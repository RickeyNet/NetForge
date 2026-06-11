"""FTD 1010 setup dialog: console day-0 wizard + FDM API staging steps."""

import threading
import tkinter as tk
from tkinter import ttk, filedialog

from netforge.serial_common import (
    BAUD_RATES,
    open_console_port,
    refresh_com_ports,
)
from netforge.ui.theme import C
from netforge.ui.win_theme import _apply_icon
from netforge.ui.helpers import (
    _ask,
    _attach_context_menu,
    _center_over,
    _dialog,
    _scrolled_text,
)
from netforge.ftd.console import (
    ERASE_TIMEOUT,
    SETUP_IDLE_TIMEOUT,
    SETUP_TIMEOUT,
    ExpectSession,
    erase_config_rules,
    initial_setup_rules,
)
from netforge.ftd.fdm_api import FdmClient, FdmError, FdmStopped


class FtdSetupDialog:
    """Automate FTD 1010 staging.

    Tab 1 drives the console first-boot wizard over a serial cable
    (login, password change, connect ftd, EULA, management network).
    Tab 2 talks to the FDM REST API over the management port to do the
    steps the config guide does in the web GUI: accept the EULA / skip
    device setup, start the 90-day evaluation, deploy, and upload +
    run a firmware upgrade.
    """

    def __init__(self, parent):
        self.parent     = parent
        self._worker    = None
        self._stop_flag = False
        self._busy      = False
        self._closing   = False
        self._ser       = None
        # Transcript scrubbing state (set per operation in _begin).
        self._active_secrets = []
        self._holdback       = 0
        self._carry          = ""

        try:
            import serial            # noqa: F401  (probe only)
            import serial.tools.list_ports  # noqa: F401
        except ImportError:
            _dialog("Missing pyserial",
                    "The 'pyserial' package is required for console "
                    "automation.\n\nInstall it with:  pip install pyserial",
                    "error")
            return

        self._build_ui()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        dlg = tk.Toplevel(self.parent)
        self.dlg = dlg
        dlg.title("FTD 1010 Setup")
        dlg.configure(bg=C["bg"])
        dlg.transient(self.parent)
        _apply_icon(dlg)
        tk.Frame(dlg, bg=C["accent"], height=3).pack(fill="x")

        inner = ttk.Frame(dlg, padding=(16, 12, 16, 14))
        inner.pack(fill="both", expand=True)

        ttk.Label(inner, text="FTD 1010 Setup",
                  style="Sec.TLabel").pack(anchor="w")
        ttk.Label(inner,
                  text="Step 1 runs the day-0 wizard over the console "
                       "cable. Step 2 connects to the management IP and "
                       "performs the FDM (web GUI) steps over its REST "
                       "API: EULA / 90-day evaluation, deploy, and "
                       "firmware upgrade.",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(2, 8))

        nb = ttk.Notebook(inner)
        nb.pack(fill="x")
        self._build_console_tab(nb)
        self._build_fdm_tab(nb)

        # ---- transcript ----
        ttk.Label(inner, text="Transcript",
                  style="Sec.TLabel").pack(anchor="w", pady=(8, 2))
        self.log = _scrolled_text(
            inner, height=14, width=90, wrap="word",
            font=("Consolas", 9),
            bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2)
        self.log.pack(fill="both", expand=True, pady=(0, 8))
        self.log.configure(state="disabled")
        _attach_context_menu(self.log)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(inner, textvariable=self.status_var,
                  style="Hint.TLabel").pack(anchor="w")

        bf = ttk.Frame(inner)
        bf.pack(fill="x", pady=(6, 0))
        self.stop_btn = ttk.Button(bf, text="Stop", command=self._stop,
                                   state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(bf, text="Close",
                   command=self._on_close).pack(side="right")

        dlg.protocol("WM_DELETE_WINDOW", self._on_close)
        dlg.geometry("760x760")
        self._refresh_ports()
        _center_over(dlg, self.parent)

    def _grid_field(self, parent, row, label, default="", show=None,
                    hint=""):
        ttk.Label(parent, text=label, width=22, anchor="w").grid(
            row=row, column=0, sticky="w", padx=4, pady=2)
        e = ttk.Entry(parent, width=30, show=show or "")
        if default:
            e.insert(0, default)
        e.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        _attach_context_menu(e)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(
                row=row, column=2, sticky="w", padx=4)
        return e

    def _build_console_tab(self, nb):
        tab = ttk.Frame(nb, padding=(10, 8))
        nb.add(tab, text="1. Console Setup (serial)")

        ttk.Label(tab, text="COM Port", width=22, anchor="w").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        self.port_cb = ttk.Combobox(tab, width=28, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(tab, text="Refresh",
                   command=self._refresh_ports).grid(
            row=0, column=2, padx=4, pady=2, sticky="w")

        ttk.Label(tab, text="Baud", width=22, anchor="w").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        self.baud_cb = ttk.Combobox(
            tab, width=28, state="readonly", values=list(BAUD_RATES))
        self.baud_cb.set("9600")
        self.baud_cb.grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        self.user_e    = self._grid_field(tab, 2, "Username", "admin")
        self.cur_pw_e  = self._grid_field(tab, 3, "Current Password",
                                          "Admin123", show="*",
                                          hint="(factory default Admin123)")
        self.new_pw_e  = self._grid_field(tab, 4, "New Password", show="*")
        self.ip_e      = self._grid_field(tab, 5, "Management IP")
        self.mask_e    = self._grid_field(tab, 6, "Netmask",
                                          "255.255.255.0")
        self.gw_e      = self._grid_field(tab, 7, "Gateway",
                                          hint="(Gateway IP)")
        self.host_e    = self._grid_field(tab, 8, "Hostname",
                                          hint="(blank = keep default)")
        self.dns_e     = self._grid_field(tab, 9, "DNS Servers",
                                          hint="(blank = keep default)")
        self.domain_e  = self._grid_field(tab, 10, "Search Domain",
                                          hint="(blank = none)")
        tab.columnconfigure(1, weight=1)

        bf = ttk.Frame(tab)
        bf.grid(row=11, column=0, columnspan=3, sticky="w",
                padx=4, pady=(8, 2))
        self.setup_btn = ttk.Button(bf, text="Run Initial Setup",
                                    command=self._start_initial_setup)
        self.setup_btn.pack(side="left")
        self.erase_btn = ttk.Button(bf, text="Erase Configuration...",
                                    command=self._start_erase)
        self.erase_btn.pack(side="left", padx=8)
        ttk.Label(tab,
                  text="Erase = recovery for login-loop / 'FTD service "
                       "not installed' (paperclip-reset first, then run).",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").grid(
            row=12, column=0, columnspan=3, sticky="w", padx=4)

    def _build_fdm_tab(self, nb):
        tab = ttk.Frame(nb, padding=(10, 8))
        nb.add(tab, text="2. FDM Setup (network)")

        self.fdm_ip_e   = self._grid_field(tab, 0, "Device IP",
                                           hint="(management IP from "
                                                "step 1)")
        self.fdm_user_e = self._grid_field(tab, 1, "Username", "admin")
        self.fdm_pw_e   = self._grid_field(tab, 2, "Password", show="*",
                                           hint="(password set in step 1)")

        ttk.Label(tab, text="Firmware Image", width=22, anchor="w").grid(
            row=3, column=0, sticky="w", padx=4, pady=2)
        self.fw_e = ttk.Entry(tab, width=30)
        self.fw_e.grid(row=3, column=1, sticky="ew", padx=4, pady=2)
        _attach_context_menu(self.fw_e)
        ttk.Button(tab, text="Browse...",
                   command=self._browse_firmware).grid(
            row=3, column=2, padx=4, pady=2, sticky="w")
        tab.columnconfigure(1, weight=1)

        bf = ttk.Frame(tab)
        bf.grid(row=4, column=0, columnspan=3, sticky="w",
                padx=4, pady=(8, 2))
        self.eula_btn = ttk.Button(
            bf, text="Accept EULA + 90-Day Eval",
            command=lambda: self._start_fdm("eula"))
        self.eula_btn.pack(side="left")
        self.deploy_btn = ttk.Button(
            bf, text="Deploy Now",
            command=lambda: self._start_fdm("deploy"))
        self.deploy_btn.pack(side="left", padx=8)
        self.upgrade_btn = ttk.Button(
            bf, text="Upload Firmware & Upgrade",
            command=lambda: self._start_fdm("upgrade"))
        self.upgrade_btn.pack(side="left")

        ttk.Label(tab,
                  text="FDM takes ~10 minutes to come up after the "
                       "console setup finishes. The upgrade installs and "
                       "reboots on its own (~45 minutes); the API drops "
                       "mid-upgrade, which is normal.",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=4)

    def _refresh_ports(self):
        refresh_com_ports(self.port_cb)

    def _browse_firmware(self):
        path = filedialog.askopenfilename(
            parent=self.dlg, title="Select FTD upgrade image",
            filetypes=[("FTD upgrade image", "*.sh *.REL.tar *.tar"),
                       ("All files", "*.*")])
        if path:
            self.fw_e.delete(0, "end")
            self.fw_e.insert(0, path)

    # ---------------------------------------------------------- logging
    def _log(self, msg, final=False):
        """Scrub secrets and marshal transcript text to the UI thread.

        A device may echo a password back split across read chunks, so
        the last ``_holdback`` characters are carried over and re-checked
        against the next message instead of being displayed immediately;
        ``final=True`` flushes the carry at the end of an operation.
        Secrets and holdback are captured on the main thread in _begin -
        tk widgets must not be read from the worker.
        """
        if self._closing:
            return
        text = self._carry + msg
        for pw in self._active_secrets:
            if pw and pw in text:
                text = text.replace(pw, "********")
        if final or not self._holdback:
            self._carry, out = "", text
        elif len(text) <= self._holdback:
            self._carry, out = text, ""
        else:
            self._carry = text[-self._holdback:]
            out = text[:-self._holdback]
        if out:
            try:
                self.dlg.after(0, self._log_main, out)
            except Exception:
                pass  # dialog was destroyed mid-operation

    def _log_main(self, msg):
        if self._closing:
            return
        try:
            self.log.configure(state="normal")
            self.log.insert("end", msg)
            self.log.see("end")
            self.log.configure(state="disabled")
        except tk.TclError:
            pass

    def _set_status(self, text):
        if self._closing:
            return
        try:
            self.dlg.after(0, self.status_var.set, text)
        except Exception:
            pass

    # ---------------------------------------------------------- control
    def _begin(self, target, args):
        if self._busy:
            _dialog("Busy", "Another operation is still running.",
                    "warning")
            return
        self._busy      = True
        self._stop_flag = False
        self._active_secrets = [pw for pw in (self.cur_pw_e.get(),
                                              self.new_pw_e.get(),
                                              self.fdm_pw_e.get()) if pw]
        self._holdback = max(
            (len(pw) for pw in self._active_secrets), default=1) - 1
        self._carry = ""
        self.stop_btn.configure(state="normal")
        for b in (self.setup_btn, self.erase_btn, self.eula_btn,
                  self.deploy_btn, self.upgrade_btn):
            b.configure(state="disabled")
        self._worker = threading.Thread(target=target, args=args,
                                        daemon=True)
        self._worker.start()

    def _finish(self):
        self._log("", final=True)   # flush the scrub carry
        self._busy = False
        try:
            self.dlg.after(0, self._reset_buttons)
        except Exception:
            pass

    def _reset_buttons(self):
        if self._closing:
            return
        try:
            self.stop_btn.configure(state="disabled")
            for b in (self.setup_btn, self.erase_btn, self.eula_btn,
                      self.deploy_btn, self.upgrade_btn):
                b.configure(state="normal")
        except tk.TclError:
            pass

    def _stop(self):
        self._stop_flag = True
        self._set_status("Stopping...")

    def _on_close(self):
        if self._worker and self._worker.is_alive():
            if not _ask("Operation in Progress",
                        "An operation is still running. Stop and close?"):
                return
            self._stop_flag = True
            # Closing the port unblocks a worker stuck in a serial
            # read/write; the _closing flag silences its callbacks. No
            # blocking join here - it would freeze the whole UI while
            # buying nothing (the worker is a daemon thread).
            ser = self._ser
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
        self._closing = True
        self.dlg.destroy()

    # ----------------------------------------------------- console flow
    def _console_answers(self):
        return {
            "username":         self.user_e.get().strip() or "admin",
            "current_password": self.cur_pw_e.get(),
            "new_password":     self.new_pw_e.get(),
            "ip":               self.ip_e.get().strip(),
            "netmask":          self.mask_e.get().strip(),
            "gateway":          self.gw_e.get().strip(),
            "hostname":         self.host_e.get().strip(),
            "dns":              self.dns_e.get().strip(),
            "search_domain":    self.domain_e.get().strip(),
        }

    @staticmethod
    def _non_ascii_fields(answers):
        """Console answers are sent as ASCII; find any that can't be.

        Without this check a password like 'Pässw0rd!' would be silently
        sent to the device as 'P?ssw0rd!' - accepted (confirm gets the
        same mangling) but different from what the user typed.
        """
        return [key for key, val in answers.items()
                if any(ord(ch) > 127 for ch in val)]

    def _selected_port(self):
        sel = self.port_cb.get().strip()
        if not sel:
            _dialog("No COM port", "Select a COM port first.", "warning")
            return None
        return sel.split(" ", 1)[0]

    def _baud(self):
        try:
            return int(self.baud_cb.get())
        except ValueError:
            return 9600

    def _start_initial_setup(self):
        port = self._selected_port()
        if port is None:
            return
        a = self._console_answers()
        missing = [k for k in ("new_password", "ip", "netmask", "gateway")
                   if not a[k]]
        if missing:
            _dialog("Missing Fields",
                    "Fill in: " + ", ".join(
                        m.replace("_", " ") for m in missing),
                    "warning")
            return
        bad = self._non_ascii_fields(a)
        if bad:
            _dialog("Non-ASCII Characters",
                    "The console only accepts ASCII. Fix: " + ", ".join(
                        b.replace("_", " ") for b in bad),
                    "warning")
            return
        rules = initial_setup_rules(a)
        # Pre-fill the FDM tab so step 2 is one click away.
        self.fdm_ip_e.delete(0, "end")
        self.fdm_ip_e.insert(0, a["ip"])
        self.fdm_pw_e.delete(0, "end")
        self.fdm_pw_e.insert(0, a["new_password"])
        self._begin(self._run_console,
                    (port, self._baud(), rules, "Initial setup",
                     SETUP_TIMEOUT, SETUP_IDLE_TIMEOUT))

    def _start_erase(self):
        port = self._selected_port()
        if port is None:
            return
        if not _ask("Erase Configuration",
                    "This wipes the FTD back to factory defaults and "
                    "reboots it. Continue?"):
            return
        a = self._console_answers()
        if not a["new_password"]:
            # The forced password change may not trigger; reuse current.
            a["new_password"] = a["current_password"]
        bad = self._non_ascii_fields(a)
        if bad:
            _dialog("Non-ASCII Characters",
                    "The console only accepts ASCII. Fix: " + ", ".join(
                        b.replace("_", " ") for b in bad),
                    "warning")
            return
        rules = erase_config_rules(a)
        self._begin(self._run_console,
                    (port, self._baud(), rules, "Erase configuration",
                     ERASE_TIMEOUT, 300.0))

    def _run_console(self, port, baud, rules, label, timeout,
                     idle_timeout):
        try:
            self._set_status(f"Opening {port} @ {baud}...")
            self._log(f"--- {label}: opening {port} at {baud} baud ---\n")
            self._ser = open_console_port(port, baud)
            self._set_status(f"{label} running... watch the transcript")
            session = ExpectSession(
                self._ser, rules, log=self._log,
                stop=lambda: self._stop_flag,
                overall_timeout=timeout,
                idle_timeout=idle_timeout)
            result = session.run()
            if result.ok:
                self._log(f"\n--- {label} finished ({result.reason}) ---\n")
                self._set_status(f"{label} complete")
            else:
                self._log(f"\n--- {label} did not finish: "
                          f"{result.reason} ---\n"
                          f"Steps completed: "
                          f"{', '.join(result.fired) or '(none)'}\n")
                self._set_status(f"{label} stopped: {result.reason}")
        except Exception as exc:
            self._log(f"\nERROR: {exc}\n")
            self._set_status("Error - see transcript")
        finally:
            ser, self._ser = self._ser, None
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            self._finish()

    # --------------------------------------------------------- FDM flow
    def _start_fdm(self, action):
        host = self.fdm_ip_e.get().strip()
        pw   = self.fdm_pw_e.get()
        if not host or not pw:
            _dialog("Missing Fields",
                    "Device IP and password are required.", "warning")
            return
        fw = self.fw_e.get().strip()
        if action == "upgrade" and not fw:
            _dialog("Missing Firmware",
                    "Pick a firmware image first.", "warning")
            return
        user = self.fdm_user_e.get().strip() or "admin"
        self._begin(self._run_fdm, (action, host, user, pw, fw))

    def _run_fdm(self, action, host, user, pw, fw):
        client = FdmClient(host, username=user, password=pw,
                           log=self._log)
        stop = lambda: self._stop_flag  # noqa: E731
        try:
            self._set_status(f"Connecting to https://{host} ...")
            client.login()
            if action == "eula":
                self._set_status("Accepting EULA / initial provisioning...")
                client.accept_eula()
                self._set_status("Starting 90-day evaluation...")
                client.start_evaluation()
                self._set_status("EULA + evaluation done")
            elif action == "deploy":
                self._set_status("Deploying...")
                client.deploy(progress=lambda s:
                              self._set_status(f"Deploying... ({s})"),
                              stop=stop)
                self._set_status("Deploy complete")
            elif action == "upgrade":
                self._set_status("Uploading firmware...")
                last_mb = [-1]

                def upload_progress(sent, total):
                    mb = sent // (1024 * 1024)
                    if mb != last_mb[0]:
                        last_mb[0] = mb
                        self._set_status(
                            f"Uploading firmware... "
                            f"{mb}/{total // (1024 * 1024)} MB")

                client.upload_upgrade(fw, progress=upload_progress,
                                      stop=stop)
                self._set_status("Starting upgrade...")
                client.start_upgrade()
                self._set_status("Upgrade running on device (~45 min)")
            self._log(f"\n--- FDM {action} finished ---\n")
        except FdmStopped:
            self._log(f"\n--- FDM {action} stopped by user ---\n")
            self._set_status("Stopped")
        except FdmError as exc:
            self._log(f"\nFDM ERROR: {exc}\n")
            self._set_status("FDM error - see transcript")
        except Exception as exc:
            self._log(f"\nERROR: {exc}\n")
            self._set_status("Error - see transcript")
        finally:
            self._finish()
