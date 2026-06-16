"""FTD setup dialog: pre-stage (day-0 wizard + FDM API) and pre-ship."""

import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog

from netforge.data.storage import load_json, save_json
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
    PRESHIP_CAPTURE_CMDS,
    PRESHIP_IDLE_TIMEOUT,
    PRESHIP_TIMEOUT,
    SETUP_IDLE_TIMEOUT,
    SETUP_TIMEOUT,
    ExpectSession,
    capture_command,
    capture_login_rules,
    erase_config_rules,
    initial_setup_rules,
    preship_rules,
)
from netforge.ftd.fdm_api import FdmClient, FdmError, FdmStopped


class FtdSetupDialog:
    """Automate FTD staging, split into pre-stage and pre-ship.

    Pre-stage (before customer site info):
      Tab 1 drives the console first-boot wizard over a serial cable
      (login, password change, connect ftd, EULA, management network).
      Tab 2 talks to the FDM REST API over the management port to do
      the steps the config guide does in the web GUI: accept the EULA /
      skip device setup, start the 90-day evaluation, deploy, and
      upload + run a firmware upgrade.

    Pre-ship (after customer site info is obtained):
      Tab 3 goes back over the console to register the FMC manager,
      run the management-data-interface wizard, optionally disable or
      statically configure management0, then captures show output to a
      text file named with the date, site name, and S rack number.
    """

    def __init__(self, parent):
        self.parent     = parent
        self._worker    = None
        self._stop_flag = False
        self._busy      = False
        self._closing   = False
        self._ser       = None
        # Saved field profiles (IPs, masks, passwords, ...) keyed by name.
        self._profiles  = load_json("ftd_profiles.json", {})
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
        dlg.title("FTD Setup")
        dlg.configure(bg=C["bg"])
        dlg.transient(self.parent)
        _apply_icon(dlg)
        tk.Frame(dlg, bg=C["accent"], height=3).pack(fill="x")

        inner = ttk.Frame(dlg, padding=(16, 12, 16, 14))
        inner.pack(fill="both", expand=True)

        ttk.Label(inner, text="FTD Setup",
                  style="Sec.TLabel").pack(anchor="w")
        ttk.Label(inner,
                  text="Pre-stage (before customer info): step 1 runs "
                       "the day-0 wizard over the console cable; step 2 "
                       "does the FDM (web GUI) steps over its REST API: "
                       "EULA / 90-day evaluation, deploy, and firmware "
                       "upgrade. Pre-ship (after customer info): step 3 "
                       "registers the FMC manager, sets up the "
                       "management interfaces, and captures the device "
                       "config for the site records.",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(2, 8))

        # Console connection, shared by the serial tabs (1 and 3).
        conn = ttk.Frame(inner)
        conn.pack(fill="x", pady=(0, 4))
        ttk.Label(conn, text="COM Port", width=22, anchor="w").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        self.port_cb = ttk.Combobox(conn, width=28, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(conn, text="Refresh",
                   command=self._refresh_ports).grid(
            row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Label(conn, text="Baud", width=22, anchor="w").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        self.baud_cb = ttk.Combobox(
            conn, width=28, state="readonly", values=list(BAUD_RATES))
        self.baud_cb.set("9600")
        self.baud_cb.grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        conn.columnconfigure(1, weight=1)

        nb = ttk.Notebook(inner)
        nb.pack(fill="x")
        self._build_console_tab(nb)
        self._build_fdm_tab(nb)
        self._build_preship_tab(nb)
        # Built after the tabs (their fields must exist), but shown with
        # the connection settings since a profile spans every tab.
        self._build_profile_bar(inner, before=nb)
        self._action_btns = (self.setup_btn, self.erase_btn,
                             self.eula_btn, self.deploy_btn,
                             self.upgrade_btn, self.preship_btn,
                             self.capture_btn)

        # ---- transcript ----
        ttk.Label(inner, text="Transcript",
                  style="Sec.TLabel").pack(anchor="w", pady=(8, 2))
        self.log = _scrolled_text(
            inner, height=10, width=90, wrap="word",
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
        dlg.geometry("780x900")
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
        nb.add(tab, text="1. Pre-Stage: Console (serial)")

        self.user_e    = self._grid_field(tab, 0, "Username", "admin")
        self.cur_pw_e  = self._grid_field(tab, 1, "Current Password",
                                          "Admin123", show="*",
                                          hint="(factory default Admin123)")
        self.new_pw_e  = self._grid_field(tab, 2, "New Password", show="*")
        self.ip_e      = self._grid_field(tab, 3, "Management IP")
        self.mask_e    = self._grid_field(tab, 4, "Netmask",
                                          "255.255.255.0")
        self.gw_e      = self._grid_field(tab, 5, "Gateway",
                                          hint="(Gateway IP)")
        self.host_e    = self._grid_field(tab, 6, "Hostname",
                                          hint="(blank = keep default)")
        self.dns_e     = self._grid_field(tab, 7, "DNS Servers",
                                          hint="(blank = keep default)")
        self.domain_e  = self._grid_field(tab, 8, "Search Domain",
                                          hint="(blank = none)")
        tab.columnconfigure(1, weight=1)

        bf = ttk.Frame(tab)
        bf.grid(row=9, column=0, columnspan=3, sticky="w",
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
            row=10, column=0, columnspan=3, sticky="w", padx=4)

    def _build_fdm_tab(self, nb):
        tab = ttk.Frame(nb, padding=(10, 8))
        nb.add(tab, text="2. Pre-Stage: FDM (network)")

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

    def _build_preship_tab(self, nb):
        tab = ttk.Frame(nb, padding=(10, 8))
        nb.add(tab, text="3. Pre-Ship (serial)")

        self.ps_pw_e  = self._grid_field(tab, 0, "Admin Password",
                                         show="*",
                                         hint="(set during pre-stage)")
        self.ps_fmc_e = self._grid_field(tab, 1, "FMC IP")
        self.ps_key_e = self._grid_field(tab, 2, "Registration Key")

        self.ps_data_var = tk.IntVar(value=1)
        ttk.Checkbutton(tab,
                        text="Configure data interface as management "
                             "(uncheck for HA)",
                        variable=self.ps_data_var).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=4,
            pady=(6, 2))
        self.ps_iface_e = self._grid_field(tab, 4, "Data Interface",
                                           "Ethernet1/1")
        self.ps_name_e  = self._grid_field(tab, 5, "Interface Name")
        self.ps_ip_e    = self._grid_field(tab, 6, "IP Address")
        self.ps_mask_e  = self._grid_field(tab, 7, "Netmask",
                                           "255.255.255.252",
                                           hint="(/30)")
        self.ps_gw_e    = self._grid_field(tab, 8, "Gateway")
        self.ps_dns_e   = self._grid_field(tab, 9, "DNS Servers",
                                           "0.0.0.0")
        self.ps_ddns_e  = self._grid_field(tab, 10, "DDNS Update URL",
                                           "none")

        self.ps_disable_var = tk.IntVar(value=0)
        ttk.Checkbutton(tab,
                        text="Disable management0 (do NOT use for HA)",
                        variable=self.ps_disable_var).grid(
            row=11, column=0, columnspan=3, sticky="w", padx=4,
            pady=(6, 2))
        self.ps_dedic_var = tk.IntVar(value=0)
        ttk.Checkbutton(tab,
                        text="Configure dedicated management0 "
                             "(2100/3100 series)",
                        variable=self.ps_dedic_var).grid(
            row=12, column=0, columnspan=3, sticky="w", padx=4)
        self.ps_mgmt_e = self._grid_field(tab, 13,
                                          "Mgmt0 IP / Mask / GW",
                                          hint="(space-separated)")

        ttk.Label(tab, text="Site Name", width=22, anchor="w").grid(
            row=14, column=0, sticky="w", padx=4, pady=2)
        self.ps_site_e = ttk.Entry(tab, width=30)
        self.ps_site_e.grid(row=14, column=1, sticky="ew",
                            padx=4, pady=2)
        _attach_context_menu(self.ps_site_e)
        rackf = ttk.Frame(tab)
        rackf.grid(row=14, column=2, sticky="w", padx=4)
        ttk.Label(rackf, text="S Rack #").pack(side="left")
        self.ps_rack_e = ttk.Entry(rackf, width=10)
        self.ps_rack_e.pack(side="left", padx=(6, 0))
        _attach_context_menu(self.ps_rack_e)
        tab.columnconfigure(1, weight=1)

        self.ps_capture_var = tk.IntVar(value=1)
        ttk.Checkbutton(tab,
                        text="Capture device config when finished "
                             "(named date + site + rack)",
                        variable=self.ps_capture_var).grid(
            row=15, column=0, columnspan=3, sticky="w", padx=4,
            pady=(6, 2))

        bf = ttk.Frame(tab)
        bf.grid(row=16, column=0, columnspan=3, sticky="w",
                padx=4, pady=(8, 2))
        self.preship_btn = ttk.Button(bf, text="Run Pre-Ship Config",
                                      command=self._start_preship)
        self.preship_btn.pack(side="left")
        self.capture_btn = ttk.Button(
            bf, text="Capture Config Only",
            command=lambda: self._start_preship(capture_only=True))
        self.capture_btn.pack(side="left", padx=8)
        ttk.Label(tab,
                  text="Runs over the console: configure manager add, "
                       "then the management-data-interface wizard and "
                       "any management0 steps, then captures show "
                       "managers / network / routes / version.",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").grid(
            row=17, column=0, columnspan=3, sticky="w", padx=4)

    # --------------------------------------------------------- profiles
    def _build_profile_bar(self, parent, before=None):
        # pack(before=None) is an error, so only pass it when anchored.
        anchor = {"before": before} if before is not None else {}
        pf = ttk.Frame(parent)
        pf.pack(fill="x", pady=(0, 6), **anchor)
        ttk.Label(pf, text="Profile", width=22, anchor="w").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        self.profile_cb = ttk.Combobox(pf, width=28)
        self.profile_cb.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        self.profile_cb.bind("<<ComboboxSelected>>", self._load_profile)
        _attach_context_menu(self.profile_cb)
        ttk.Button(pf, text="Save", command=self._save_profile).grid(
            row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Button(pf, text="Delete", style="Del.TButton",
                   command=self._delete_profile).grid(
            row=0, column=3, padx=4, pady=2, sticky="w")
        pf.columnconfigure(1, weight=1)
        ttk.Label(parent,
                  text="Save the fields above (IPs, masks, passwords, "
                       "interfaces) under a name to reuse them. Type a "
                       "name and click Save; pick one to load it.",
                  style="Hint.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(0, 4), **anchor)
        self._refresh_profiles()

    def _profile_fields(self):
        """Form fields persisted in a profile, keyed by stable names.

        Returns (text-entry widgets, checkbox IntVars). The site name and
        S rack number are per-device labels for the capture file, not
        reusable settings, so they are deliberately left out.
        """
        entries = {
            "username":          self.user_e,
            "current_password":  self.cur_pw_e,
            "new_password":      self.new_pw_e,
            "ip":                self.ip_e,
            "netmask":           self.mask_e,
            "gateway":           self.gw_e,
            "hostname":          self.host_e,
            "dns":               self.dns_e,
            "search_domain":     self.domain_e,
            "fdm_ip":            self.fdm_ip_e,
            "fdm_username":      self.fdm_user_e,
            "fdm_password":      self.fdm_pw_e,
            "firmware":          self.fw_e,
            "ps_admin_password": self.ps_pw_e,
            "ps_fmc_ip":         self.ps_fmc_e,
            "ps_reg_key":        self.ps_key_e,
            "ps_data_iface":     self.ps_iface_e,
            "ps_iface_name":     self.ps_name_e,
            "ps_ip":             self.ps_ip_e,
            "ps_netmask":        self.ps_mask_e,
            "ps_gateway":        self.ps_gw_e,
            "ps_dns":            self.ps_dns_e,
            "ps_ddns":           self.ps_ddns_e,
            "ps_mgmt":           self.ps_mgmt_e,
        }
        checks = {
            "ps_use_data_mgmt":  self.ps_data_var,
            "ps_disable_mgmt":   self.ps_disable_var,
            "ps_dedicated_mgmt": self.ps_dedic_var,
            "ps_capture":        self.ps_capture_var,
        }
        return entries, checks

    def _collect_profile(self):
        entries, checks = self._profile_fields()
        data = {k: w.get() for k, w in entries.items()}
        data.update({k: int(v.get()) for k, v in checks.items()})
        return data

    def _apply_profile(self, data):
        entries, checks = self._profile_fields()
        for key, widget in entries.items():
            if key in data:
                widget.delete(0, "end")
                widget.insert(0, str(data[key] or ""))
        for key, var in checks.items():
            if key in data:
                try:
                    var.set(int(data[key]))
                except (TypeError, ValueError):
                    pass

    def _refresh_profiles(self, select=None):
        self.profile_cb["values"] = sorted(self._profiles)
        if select is not None:
            self.profile_cb.set(select)

    def _load_profile(self, _evt=None):
        name = self.profile_cb.get().strip()
        data = self._profiles.get(name)
        if not data:
            return
        self._apply_profile(data)
        self._set_status(f"Loaded profile '{name}'")

    def _save_profile(self):
        name = self.profile_cb.get().strip()
        if not name:
            _dialog("Name Required",
                    "Type a profile name in the box, then click Save.",
                    "warning")
            return
        if name in self._profiles and not _ask(
                "Overwrite Profile",
                f"A profile named '{name}' already exists. "
                "Overwrite it?"):
            return
        self._profiles[name] = self._collect_profile()
        save_json("ftd_profiles.json", self._profiles)
        self._refresh_profiles(select=name)
        self._set_status(f"Saved profile '{name}'")

    def _delete_profile(self):
        name = self.profile_cb.get().strip()
        if name not in self._profiles:
            _dialog("No Such Profile",
                    "Select a saved profile to delete.", "warning")
            return
        if not _ask("Delete Profile", f"Delete the profile '{name}'?"):
            return
        self._profiles.pop(name, None)
        save_json("ftd_profiles.json", self._profiles)
        self._refresh_profiles(select="")
        self._set_status(f"Deleted profile '{name}'")

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
                                              self.fdm_pw_e.get(),
                                              self.ps_pw_e.get()) if pw]
        self._holdback = max(
            (len(pw) for pw in self._active_secrets), default=1) - 1
        self._carry = ""
        self.stop_btn.configure(state="normal")
        for b in self._action_btns:
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
            for b in self._action_btns:
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
                if isinstance(val, str)
                and any(ord(ch) > 127 for ch in val)]

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

    # ---------------------------------------------------- pre-ship flow
    def _preship_answers(self):
        pw   = self.ps_pw_e.get()
        mgmt = self.ps_mgmt_e.get().split()
        return {
            "username":         "admin",
            "current_password": pw,
            # No forced password change is expected at pre-ship; if one
            # appears anyway, keep the same password.
            "new_password":     pw,
            "fmc_ip":           self.ps_fmc_e.get().strip(),
            "reg_key":          self.ps_key_e.get().strip(),
            "use_data_mgmt":    bool(self.ps_data_var.get()),
            "data_iface":       self.ps_iface_e.get().strip()
                                or "Ethernet1/1",
            "iface_name":       self.ps_name_e.get().strip(),
            "ip":               self.ps_ip_e.get().strip(),
            "netmask":          self.ps_mask_e.get().strip()
                                or "255.255.255.252",
            "gateway":          self.ps_gw_e.get().strip(),
            "dns":              self.ps_dns_e.get().strip() or "0.0.0.0",
            "ddns":             self.ps_ddns_e.get().strip() or "none",
            "disable_mgmt":     bool(self.ps_disable_var.get()),
            "dedicated_mgmt":   bool(self.ps_dedic_var.get()),
            "mgmt_ip":          mgmt[0] if len(mgmt) > 0 else "",
            "mgmt_netmask":     mgmt[1] if len(mgmt) > 1 else "",
            "mgmt_gateway":     mgmt[2] if len(mgmt) > 2 else "",
        }

    def _capture_filename(self):
        parts = [datetime.now().strftime("%Y-%m-%d"),
                 self.ps_site_e.get().strip(),
                 self.ps_rack_e.get().strip()]
        name = " ".join(p for p in parts if p)
        return re.sub(r'[\\/:*?"<>|]', "_", name) + ".txt"

    def _start_preship(self, capture_only=False):
        port = self._selected_port()
        if port is None:
            return
        a = self._preship_answers()
        missing = []
        if not a["current_password"]:
            missing.append("admin password")
        if not capture_only:
            if not a["fmc_ip"]:
                missing.append("FMC IP")
            if not a["reg_key"]:
                missing.append("registration key")
            if a["use_data_mgmt"]:
                missing += [lbl for lbl, key in
                            (("interface name", "iface_name"),
                             ("IP address", "ip"),
                             ("gateway", "gateway"))
                            if not a[key]]
            if a["dedicated_mgmt"] and not (a["mgmt_ip"]
                                            and a["mgmt_netmask"]
                                            and a["mgmt_gateway"]):
                missing.append("mgmt0 IP / mask / gateway")
        if missing:
            _dialog("Missing Fields",
                    "Fill in: " + ", ".join(missing), "warning")
            return
        bad = self._non_ascii_fields(a)
        if bad:
            _dialog("Non-ASCII Characters",
                    "The console only accepts ASCII. Fix: " + ", ".join(
                        b.replace("_", " ") for b in bad),
                    "warning")
            return
        if capture_only:
            rules, label = capture_login_rules(a), "Pre-ship capture"
        else:
            rules, label = preship_rules(a), "Pre-ship config"
        do_capture = capture_only or bool(self.ps_capture_var.get())
        self._begin(self._run_preship,
                    (port, self._baud(), rules, label, do_capture,
                     self._capture_filename()))

    def _run_preship(self, port, baud, rules, label, do_capture, fname):
        try:
            self._set_status(f"Opening {port} @ {baud}...")
            self._log(f"--- {label}: opening {port} at {baud} baud ---\n")
            self._ser = open_console_port(port, baud)
            self._set_status(f"{label} running... watch the transcript")
            session = ExpectSession(
                self._ser, rules, log=self._log,
                stop=lambda: self._stop_flag,
                overall_timeout=PRESHIP_TIMEOUT,
                idle_timeout=PRESHIP_IDLE_TIMEOUT)
            result = session.run()
            if not result.ok:
                self._log(f"\n--- {label} did not finish: "
                          f"{result.reason} ---\n"
                          f"Steps completed: "
                          f"{', '.join(result.fired) or '(none)'}\n")
                self._set_status(f"{label} stopped: {result.reason}")
                return
            self._log(f"\n--- {label} finished ({result.reason}) ---\n")
            if do_capture and not self._stop_flag:
                self._set_status("Capturing device config...")
                captures = []
                for cmd in PRESHIP_CAPTURE_CMDS:
                    if self._stop_flag:
                        break
                    self._log(f"\n--- Capturing: {cmd} ---\n")
                    out = capture_command(
                        self._ser, cmd, log=self._log,
                        stop=lambda: self._stop_flag)
                    captures.append((cmd, out))
                if captures:
                    blob = self._capture_blob(captures)
                    try:
                        self.dlg.after(0, self._prompt_save_captures,
                                       blob, fname)
                    except Exception:
                        pass  # dialog was destroyed mid-operation
            self._set_status(f"{label} complete")
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

    @staticmethod
    def _capture_blob(captures):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sep = "=" * 66
        return "".join(f"{sep}\n {cmd}   ({stamp})\n{sep}\n{out}\n\n"
                       for cmd, out in captures)

    def _prompt_save_captures(self, blob, initial):
        if self._closing:
            return
        path = filedialog.asksaveasfilename(
            parent=self.dlg, defaultextension=".txt",
            initialfile=initial,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
            title="Save device config capture")
        # final=True: the operation already finished, so don't let the
        # secret-scrub holdback sit on the tail of these messages.
        if not path:
            self._log("\n--- Capture not saved (no file chosen) ---\n",
                      final=True)
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(blob)
            self._log(f"\n--- Capture saved to {path} ---\n", final=True)
        except Exception as exc:
            self._log(f"\nERROR writing capture: {exc}\n", final=True)

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
