"""Console push dialog: stream generated config over a COM port."""

import re
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

class _SerialPushDialog:
    """Push a generated config to a switch over its console port.

    Streams the config line-by-line over a COM port, waiting for the
    switch's prompt between sends so we don't overrun a slow console.
    Lives in its own worker thread; the UI just shows progress and
    transcript.
    """

    # Prompts the worker treats as "switch is ready for the next line".
    # Matched against the tail of the receive buffer.
    _PROMPT_RE = re.compile(rb"[\r\n][\w.\-]+[>#](?:\([^)]+\))?[>#]?\s*$|"
                            rb"[\w.\-]+(?:\([^)]+\))?[>#]\s*$")
    # Common day-0 setup-dialog question on factory-fresh IOS
    _SETUP_RE  = re.compile(rb"initial configuration dialog\? \[yes/no\]:")
    # Password prompt for `enable`
    _PASS_RE   = re.compile(rb"[Pp]assword:\s*$")

    # Show commands captured after a successful push, in order.
    _CAPTURE_CMDS = ("show version",
                     "show interfaces status",
                     "show running-config")

    def __init__(self, parent, config_text, hostname="", save_path=None):
        self.parent      = parent
        self.config_text = config_text
        self.hostname    = hostname
        self.save_path   = save_path
        self._ser        = None
        self._worker     = None
        self._stop_flag  = False

        try:
            import serial            # noqa: F401  (probe only)
            import serial.tools.list_ports  # noqa: F401
        except ImportError:
            _dialog("Missing pyserial",
                    "The 'pyserial' package is required for console push.\n\n"
                    "Install it with:  pip install pyserial",
                    "error")
            return

        self._build_ui()

    # --------------------------------------------------- UI
    def _build_ui(self):
        dlg = tk.Toplevel(self.parent)
        self.dlg = dlg
        dlg.title("Push Config to Switch (Console)")
        dlg.configure(bg=C["bg"])
        dlg.transient(self.parent)
        _apply_icon(dlg)
        tk.Frame(dlg, bg=C["accent"], height=3).pack(fill="x")

        inner = ttk.Frame(dlg, padding=(16, 12, 16, 14))
        inner.pack(fill="both", expand=True)

        ttk.Label(inner, text="Push Config to Switch (Console)",
                  style="Sec.TLabel").pack(anchor="w")
        ttk.Label(inner,
                  text="Connect a USB-to-serial cable to the switch console "
                       "port, then pick the COM port below.",
                  style="Hint.TLabel", wraplength=460,
                  justify="left").pack(anchor="w", pady=(2, 10))

        # ---- connection settings ----
        cf = ttk.Frame(inner)
        cf.pack(fill="x", pady=(0, 6))

        ttk.Label(cf, text="COM Port", width=18, anchor="w").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)
        self.port_cb = ttk.Combobox(cf, width=28, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(cf, text="Refresh",
                   command=self._refresh_ports).grid(
            row=0, column=2, padx=4, pady=2)

        ttk.Label(cf, text="Baud", width=18, anchor="w").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        self.baud_cb = ttk.Combobox(
            cf, width=28, state="readonly", values=list(BAUD_RATES))
        self.baud_cb.set("9600")
        self.baud_cb.grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        ttk.Label(cf, text="Enable Password", width=18, anchor="w").grid(
            row=2, column=0, sticky="w", padx=4, pady=2)
        self.enable_pw = ttk.Entry(cf, width=30, show="*")
        self.enable_pw.grid(row=2, column=1, sticky="ew", padx=4, pady=2)
        _attach_context_menu(self.enable_pw)
        ttk.Label(cf, text="(only if already set)",
                  style="Hint.TLabel").grid(
            row=2, column=2, sticky="w", padx=4)

        ttk.Label(cf, text="Line Delay (ms)", width=18, anchor="w").grid(
            row=3, column=0, sticky="w", padx=4, pady=2)
        self.delay_e = ttk.Entry(cf, width=10)
        self.delay_e.insert(0, "0")
        self.delay_e.grid(row=3, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(cf, text="(extra pause per line; 0 = as fast as the "
                           "switch echoes)",
                  style="Hint.TLabel").grid(
            row=3, column=2, sticky="w", padx=4)

        self.save_var = tk.IntVar(value=1)
        ttk.Checkbutton(cf, text="Run 'write memory' when finished",
                        variable=self.save_var).grid(
            row=4, column=1, sticky="w", padx=4, pady=(4, 2))

        self.capture_var = tk.IntVar(value=1)
        ttk.Checkbutton(
            cf,
            text="Capture show version / interfaces status / running-config",
            variable=self.capture_var).grid(
            row=5, column=1, sticky="w", padx=4, pady=(0, 2))
        ttk.Label(cf, text="(saved to the config's file)",
                  style="Hint.TLabel").grid(
            row=5, column=2, sticky="w", padx=4)

        cf.columnconfigure(1, weight=1)

        # ---- transcript ----
        ttk.Label(inner, text="Transcript",
                  style="Sec.TLabel").pack(anchor="w", pady=(8, 2))
        self.log = _scrolled_text(
            inner, height=16, width=80, wrap="word",
            font=("Consolas", 9),
            bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2)
        self.log.pack(fill="both", expand=True, pady=(0, 8))
        self.log.configure(state="disabled")
        _attach_context_menu(self.log)

        # ---- status + buttons ----
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(inner, textvariable=self.status_var,
                  style="Hint.TLabel").pack(anchor="w")

        bf = ttk.Frame(inner)
        bf.pack(fill="x", pady=(6, 0))
        self.start_btn = ttk.Button(bf, text="Start Push",
                                    command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn  = ttk.Button(bf, text="Stop",
                                    command=self._stop,
                                    state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(bf, text="Close",
                   command=self._on_close).pack(side="right")

        dlg.protocol("WM_DELETE_WINDOW", self._on_close)
        dlg.geometry("640x600")
        self._refresh_ports()

        _center_over(dlg, self.parent)

    def _refresh_ports(self):
        refresh_com_ports(self.port_cb)

    # --------------------------------------------------- logging
    def _log(self, msg, tag=None):
        # Scrub the enable password if a device echoed it back into a
        # buffer we're about to display.
        pw = getattr(self, "_active_enable_pw", "")
        if pw and isinstance(msg, str) and pw in msg:
            msg = msg.replace(pw, "********")
        # Always marshal to the UI thread.
        self.dlg.after(0, self._log_main, msg, tag)

    def _log_main(self, msg, tag):
        self.log.configure(state="normal")
        self.log.insert("end", msg)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text):
        self.dlg.after(0, self.status_var.set, text)

    # --------------------------------------------------- control
    def _start(self):
        sel = self.port_cb.get().strip()
        if not sel:
            _dialog("No COM port", "Select a COM port first.", "warning")
            return
        port = sel.split(" ", 1)[0]
        try:
            baud = int(self.baud_cb.get())
        except ValueError:
            baud = 9600
        try:
            line_delay = max(0, int(self.delay_e.get())) / 1000.0
        except ValueError:
            line_delay = 0.05

        if not self.config_text.strip():
            _dialog("Empty", "Generate a config first.", "warning")
            return

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._stop_flag = False

        import threading
        self._worker = threading.Thread(
            target=self._run,
            args=(port, baud, self.enable_pw.get(), line_delay,
                  bool(self.save_var.get()),
                  bool(self.capture_var.get())),
            daemon=True)
        self._worker.start()

    def _stop(self):
        self._stop_flag = True
        self._set_status("Stopping...")

    def _on_close(self):
        # Don't allow close while a push is mid-flight - too easy to
        # leave the switch in a half-configured state by accident.
        if self._worker and self._worker.is_alive():
            if not _ask("Push in Progress",
                        "A push is still running. Stop and close?"):
                return
            self._stop_flag = True
            self._worker.join(timeout=2)
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self.dlg.destroy()

    # --------------------------------------------------- worker
    def _run(self, port, baud, enable_pw, line_delay, do_save,
             do_capture=False):
        # Remember the enable password so _log can scrub it from any raw
        # device buffer we echo into the transcript (a non-standard console
        # or terminal server may echo the password back).
        self._active_enable_pw = enable_pw or ""
        try:
            self._set_status(f"Opening {port} @ {baud}...")
            self._log(f"--- Opening {port} at {baud} baud ---\n")
            self._ser = open_console_port(port, baud)
        except Exception as exc:
            self._log(f"ERROR: {exc}\n")
            self._set_status("Failed to open port")
            self._finish()
            return

        try:
            # Nudge the switch so it shows its prompt
            self._ser.write(b"\r\n")
            buf = self._drain(0.7)

            # Day-0 setup dialog?
            if self._SETUP_RE.search(buf):
                self._log("Detected setup dialog - answering 'no'\n")
                self._ser.write(b"no\r\n")
                self._drain(1.5)
                self._ser.write(b"\r\n")
                buf = self._drain(0.7)

            # Make sure we're in privileged exec
            if not self._ensure_enable(enable_pw):
                self._set_status("Could not enter enable mode")
                self._finish()
                return

            # Quiet the session: stop pagination and console logging chatter
            self._send_line("terminal length 0", expect_prompt=True)
            self._send_line("terminal width 511", expect_prompt=True)

            # Push the config
            self._set_status("Pushing config...")
            lines = [ln.rstrip() for ln in self.config_text.splitlines()]
            total = len(lines)
            for i, line in enumerate(lines, 1):
                if self._stop_flag:
                    self._log("\n--- Stopped by user ---\n")
                    self._set_status("Stopped")
                    self._finish()
                    return
                # Skip blank lines - they confuse some IOS prompts.
                if not line.strip():
                    continue
                # Lines starting with '!' are comments - safe to send,
                # IOS just echoes them back.
                self._send_line(line, expect_prompt=True,
                                line_delay=line_delay)
                if i % 25 == 0 or i == total:
                    self._set_status(f"Pushing config... ({i}/{total})")

            # Exit config mode in case the last line left us inside one
            self._send_line("end", expect_prompt=True)

            if do_save:
                self._set_status("Saving to startup-config...")
                self._log("\n--- Saving (write memory) ---\n")
                self._ser.write(b"write memory\r\n")
                # write memory can take several seconds
                self._drain(8.0)

            if do_capture and not self._stop_flag:
                self._capture_show_outputs()

            self._set_status("Done")
            self._log("\n--- Push complete ---\n")
        except Exception as exc:
            self._log(f"\nERROR: {exc}\n")
            self._set_status("Error - see transcript")
        finally:
            self._finish()

    def _finish(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self.dlg.after(0, self._reset_buttons)

    def _reset_buttons(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    # --------------------------------------------------- serial helpers
    def _drain(self, settle_seconds):
        """Read whatever the switch has sent, up to settle_seconds of silence."""
        import time
        buf = bytearray()
        deadline = time.monotonic() + settle_seconds
        while time.monotonic() < deadline:
            # Read only what's already buffered so we don't block for the
            # full serial timeout on every idle poll; read(1) blocks just
            # long enough to notice the next byte arrive.
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf.extend(chunk)
                deadline = time.monotonic() + settle_seconds
            elif self._stop_flag:
                break
        if buf:
            try:
                self._log(buf.decode("utf-8", errors="replace"))
            except Exception:
                pass
        return bytes(buf)

    def _send_line(self, text, expect_prompt=False, line_delay=0.0,
                   timeout=4.0):
        """Write one line and (optionally) wait for the prompt to return.

        With prompt-pacing on we return the instant the switch's prompt
        comes back rather than blocking for a fixed serial timeout, so the
        push runs as fast as the console will echo. ``line_delay`` is an
        optional extra pause after each line for finicky consoles.
        """
        import time
        self._ser.write(text.encode("ascii", errors="replace") + b"\r\n")
        if not expect_prompt:
            if line_delay:
                time.sleep(line_delay)
            self._drain(0.05)
            return b""
        deadline   = time.monotonic() + timeout
        buf        = bytearray()
        got_prompt = False
        while time.monotonic() < deadline:
            # Drain only the bytes already waiting; read(1) blocks just long
            # enough to catch the next byte instead of the full timeout.
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf.extend(chunk)
                if self._PROMPT_RE.search(buf[-200:]):
                    got_prompt = True
                    break
            if self._stop_flag:
                break
        if buf:
            self._log(buf.decode("utf-8", errors="replace"))
        if not got_prompt:
            # No prompt echoed back (slow/quiet console) - pause so we don't
            # overrun the next line.
            time.sleep(max(line_delay, 0.05))
        elif line_delay:
            time.sleep(line_delay)
        return bytes(buf)

    # --------------------------------------------------- show capture
    def _capture(self, cmd, timeout=30.0):
        """Run a show command and return its full decoded output.

        Assumes pagination is already off (`terminal length 0`), so the
        only prompt we see is the one that follows the complete output.
        Reads until that prompt reappears and the line goes quiet.
        """
        import time
        # Clear any stray bytes still in the buffer from the prior command.
        self._drain(0.2)
        self._log(f"\n--- Capturing: {cmd} ---\n")
        self._ser.write(cmd.encode("ascii", errors="replace") + b"\r\n")
        deadline    = time.monotonic() + timeout
        buf         = bytearray()
        quiet_until = None
        while time.monotonic() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf.extend(chunk)
                # Once the trailing prompt shows up, wait a short grace
                # period for any final bytes, then stop.
                if self._PROMPT_RE.search(buf[-200:]):
                    quiet_until = time.monotonic() + 0.4
            elif quiet_until is not None and time.monotonic() >= quiet_until:
                break
            if self._stop_flag:
                break
        text = buf.decode("utf-8", errors="replace")
        self._log(text)
        return self._clean_capture(cmd, text)

    @staticmethod
    def _clean_capture(cmd, text):
        """Strip the echoed command and the trailing device prompt."""
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        # Drop a leading line that is just the echoed command.
        if lines and cmd in lines[0]:
            lines = lines[1:]
        # Drop a trailing line that is just a device prompt (e.g. "Switch#").
        while lines and re.match(r"^[\w.\-]+(\([^)]+\))?[>#]\s*$", lines[-1]):
            lines.pop()
        return "\n".join(lines).strip("\n")

    def _capture_show_outputs(self):
        """Run each show command and persist the outputs to the config file."""
        self._set_status("Capturing show output...")
        captures = []
        for cmd in self._CAPTURE_CMDS:
            if self._stop_flag:
                break
            captures.append((cmd, self._capture(cmd)))
        if not captures:
            return

        from datetime import datetime
        stamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host   = self.hostname or "switch"
        blocks = [
            f"\n!{'=' * 66}\n"
            f"! {cmd}  ({host}  {stamp})\n"
            f"!{'=' * 66}\n"
            f"{out}\n"
            for cmd, out in captures
        ]
        blob = "".join(blocks)

        if self.save_path:
            try:
                with open(self.save_path, "a", encoding="utf-8") as f:
                    f.write("\n" + blob)
                self._log(f"\n--- Captures appended to {self.save_path} ---\n")
                return
            except Exception as exc:
                self._log(f"\nERROR writing captures: {exc}\n")
        # No associated file (config not saved yet) or the append failed -
        # ask the user where to drop the captured output instead.
        self.dlg.after(0, self._prompt_save_captures, blob)

    def _prompt_save_captures(self, blob):
        path = filedialog.asksaveasfilename(
            parent=self.dlg, defaultextension=".txt",
            initialfile=f"{self.hostname or 'switch'}_capture.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            title="Save captured show output")
        if not path:
            self._log("\n--- Capture not saved (no file chosen) ---\n")
            return
        try:
            # The config was never saved to a file, so write a complete
            # reference file here: the generated config followed by the
            # captured show output.
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.config_text.rstrip("\n") + "\n" + blob)
            self._log(f"\n--- Config + captures saved to {path} ---\n")
        except Exception as exc:
            self._log(f"\nERROR writing captures: {exc}\n")

    def _ensure_enable(self, enable_pw):
        """Get the switch into privileged-exec mode."""
        import time
        self._ser.write(b"\r\n")
        buf = self._drain(0.5)
        tail = buf[-200:]
        if b"#" in tail and b"(config" not in tail:
            return True
        if b">" in tail:
            self._log("Entering enable mode...\n")
            self._ser.write(b"enable\r\n")
            deadline = time.monotonic() + 3.0
            buf = bytearray()
            while time.monotonic() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    buf.extend(chunk)
                    if self._PASS_RE.search(buf[-80:]):
                        self._ser.write(
                            (enable_pw or "").encode("ascii",
                                                    errors="replace")
                            + b"\r\n")
                        self._drain(1.0)
                        break
                    if b"#" in buf[-40:]:
                        break
            if buf:
                self._log(buf.decode("utf-8", errors="replace"))
            # one more check
            self._ser.write(b"\r\n")
            final = self._drain(0.7)
            return b"#" in final[-40:]
        # No clear prompt - assume we got it, the push will fail loudly
        # if not.
        return True


# ===================================================================
#  CUSTOM THEME EDITOR
# ===================================================================
