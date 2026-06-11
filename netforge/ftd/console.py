"""FTD 1010 day-0 console automation.

Drives the interactive first-boot wizard that Cisco Firepower 1000-series
appliances present on the console port (FXOS login, forced password change,
``connect ftd``, EULA, management network, "manage locally") with a small
expect-style rule engine over a serial port. The engine is UI-free and only
needs a pyserial-like object (read / write / in_waiting), so it can be
unit-tested with a fake port.
"""

import re
import time

# Flow timeouts, shared with the dialog. First boot is slow: after
# ``connect ftd`` the appliance can sit at "System initialization in
# progress" with a silent console for 10-15 minutes before the EULA
# appears, so the setup idle timeout has to comfortably exceed that.
SETUP_TIMEOUT      = 1800.0
SETUP_IDLE_TIMEOUT = 1200.0
ERASE_TIMEOUT      = 600.0


class Rule:
    """When *pattern* matches the unconsumed tail of the buffer, respond.

    ``response`` may be:
      str   -> sent followed by CR+LF; "" sends a bare CR+LF, i.e.
               "accept the default" for wizard questions
      bytes -> sent raw, no line ending (e.g. b" " to page the EULA)
      None  -> nothing is sent; used for terminal "we're done" rules
    ``requires`` names another rule that must already have fired before
    this one becomes eligible - it keeps generic patterns (like a bare
    ``>`` prompt) from matching too early.
    """

    def __init__(self, name, pattern, response, max_fires=3,
                 terminal=False, requires=None):
        self.name      = name
        self.pattern   = re.compile(pattern, re.IGNORECASE)
        self.response  = response
        self.max_fires = max_fires
        self.terminal  = terminal
        self.requires  = requires
        self.fires     = 0


class ExpectResult:
    def __init__(self, ok, reason, fired):
        self.ok     = ok
        self.reason = reason
        self.fired  = fired

    def __repr__(self):
        return f"ExpectResult(ok={self.ok}, reason={self.reason!r})"


class ExpectSession:
    """Run a rule set against a serial port until a terminal rule fires.

    Reads only buffered bytes (same pacing trick as the IOS console push)
    so prompts are answered the instant they appear. While nothing has
    matched yet the session periodically nudges the console with CR+LF to
    wake a sleeping login prompt; once the dialog is underway it stays
    quiet, because the wizard legitimately goes silent for minutes during
    system initialization.

    Received text is coalesced and handed to ``log`` in batches (on rule
    fire, on a short flush interval, or when a batch grows large) rather
    than per read chunk - a console at 9600 baud would otherwise produce
    hundreds of one-byte log calls per second and flood a UI event loop.
    """

    _WINDOW         = 600   # bytes of unconsumed tail scanned for prompts
    _FLUSH_INTERVAL = 0.15  # seconds a log batch may sit before flushing
    _FLUSH_SIZE     = 2048  # flush a batch once it grows past this

    def __init__(self, ser, rules, log=None, stop=None,
                 overall_timeout=900.0, idle_timeout=300.0,
                 nudge_interval=2.0, max_nudges=5):
        self.ser   = ser
        self.rules = rules
        self.log   = log or (lambda _msg: None)
        self.stop  = stop or (lambda: False)
        self.overall_timeout = overall_timeout
        self.idle_timeout    = idle_timeout
        self.nudge_interval  = nudge_interval
        self.max_nudges      = max_nudges
        self.fired = []
        self._pending    = []
        self._pending_t0 = 0.0
        self._pending_n  = 0

    # ------------------------------------------------------------- run
    def run(self):
        try:
            return self._run()
        finally:
            self._flush_log()

    def _run(self):
        start     = time.monotonic()
        buf       = bytearray()
        scan_from = 0
        last_rx   = time.monotonic()
        nudges    = 0

        while True:
            if self.stop():
                return ExpectResult(False, "stopped by user", self.fired)
            now = time.monotonic()
            if now - start > self.overall_timeout:
                return ExpectResult(False, "overall timeout", self.fired)
            if self.fired and now - last_rx > self.idle_timeout:
                return ExpectResult(
                    False, "console went quiet (idle timeout)", self.fired)
            if (self._pending
                    and now - self._pending_t0 >= self._FLUSH_INTERVAL):
                self._flush_log()

            chunk = self.ser.read(getattr(self.ser, "in_waiting", 0) or 1)
            if not chunk:
                # Don't depend on the port blocking for pacing: a
                # non-blocking port would otherwise spin this loop hot.
                time.sleep(0.01)
                if (not self.fired and nudges < self.max_nudges
                        and now - last_rx > self.nudge_interval):
                    self.ser.write(b"\r\n")
                    nudges += 1
                    last_rx = now
                continue

            buf.extend(chunk)
            last_rx = time.monotonic()
            self._emit(chunk.decode("utf-8", errors="replace"))

            # Scan only the unconsumed tail, sliced before copying so a
            # long silent boot log doesn't make each scan O(buffer).
            lo = max(scan_from, len(buf) - self._WINDOW)
            window = bytes(buf[lo:])
            rule = self._match(window)
            if rule is None:
                continue

            rule.fires += 1
            self.fired.append(rule.name)
            if rule.response is not None:
                self._respond(rule)
            self._flush_log()
            scan_from = len(buf)
            if rule.terminal:
                return ExpectResult(True, rule.name, self.fired)

    def _match(self, window):
        for rule in self.rules:
            if rule.fires >= rule.max_fires:
                continue
            if rule.requires and rule.requires not in self.fired:
                continue
            if rule.pattern.search(window):
                return rule
        return None

    def _respond(self, rule):
        if isinstance(rule.response, bytes):
            self.ser.write(rule.response)
            return
        self.ser.write(
            rule.response.encode("ascii", errors="replace") + b"\r\n")
        shown = rule.response if rule.response else "<Enter>"
        self._emit(f"\n[netforge: {rule.name} -> {shown}]\n")

    # --------------------------------------------------------- logging
    def _emit(self, text):
        if not self._pending:
            self._pending_t0 = time.monotonic()
        self._pending.append(text)
        self._pending_n += len(text)
        if self._pending_n >= self._FLUSH_SIZE:
            self._flush_log()

    def _flush_log(self):
        if self._pending:
            self.log("".join(self._pending))
            self._pending.clear()
            self._pending_n = 0


# ---------------------------------------------------------------------------
# Rule sets
# ---------------------------------------------------------------------------
def _fxos_login_rules(a):
    """FXOS login + forced-password-change rules shared by every flow.

    The patterns encode hard-won prompt quirks; keep them in one place:
    "Enter new password:" / "New password:" but NOT "Confirm new
    password:" (the confirm rule owns that), and a lookbehind so a
    "Last login: ..." banner can't satisfy the login prompt.
    """
    return [
        Rule("new-pass",
             rb"(?:enter\s+|[\r\n])new password:\s*$",
             a["new_password"], max_fires=4),
        Rule("confirm-pass",
             rb"(?:confirm|retype)[^\r\n]*password:\s*$",
             a["new_password"], max_fires=4),
        Rule("login", rb"(?<!last )login:\s*$", a["username"],
             max_fires=3),
        Rule("password", rb"password:\s*$",
             a["current_password"], max_fires=3),
    ]


def initial_setup_rules(answers):
    """Rules for the FTD first-boot wizard.

    ``answers`` keys: username, current_password, new_password, ip,
    netmask, gateway, and optionally hostname / dns / search_domain
    (blank means "accept the device default"; search_domain falls back
    to the literal answer ``none``).
    """
    a = answers
    return [
        # EULA paging has to outrank everything else.
        Rule("eula-more",    rb"--More--\s*$", b" ", max_fires=500),
        Rule("eula-display", rb"Press <ENTER> to display the EULA", ""),
        Rule("eula-agree",   rb"AGREE to the EULA[^\r\n]*:?\s*$", "YES"),
        *_fxos_login_rules(a),
        # FXOS supervisor prompt -> drop into the FTD CLI.
        Rule("connect-ftd", rb"[\r\n]firepower#\s*$", "connect ftd",
             max_fires=1),
        # The network wizard proper.
        Rule("ipv4",        rb"configure IPv4\? \(y/n\)[^\r\n]*:\s*$", "y"),
        Rule("ipv6",        rb"configure IPv6\? \(y/n\)[^\r\n]*:\s*$", "n"),
        Rule("dhcp-manual", rb"\(dhcp/manual\)[^\r\n]*:\s*$", "manual"),
        Rule("mgmt-ip",
             rb"IPv4 address for the management interface[^\r\n]*:\s*$",
             a["ip"]),
        Rule("netmask", rb"IPv4 netmask[^\r\n]*:\s*$", a["netmask"]),
        Rule("gateway", rb"IPv4 default gateway[^\r\n]*:\s*$", a["gateway"]),
        Rule("hostname",
             rb"fully qualified hostname[^\r\n]*:\s*$",
             a.get("hostname", "")),
        Rule("dns", rb"DNS servers[^\r\n]*:\s*$", a.get("dns", "")),
        Rule("search-domain",
             rb"search domains[^\r\n]*:\s*$",
             a.get("search_domain") or "none"),
        Rule("manage-local",
             rb"manage the device locally\? ?\(yes/no\)[^\r\n]*:?\s*$",
             "yes"),
        # Success: wizard finished (or dropped us at the FTD CLI prompt).
        Rule("setup-complete",
             rb"successfully performed firstboot|[\r\n]>\s*$",
             None, terminal=True, requires="manage-local"),
        # connect ftd landed straight at '>' with no wizard - the device
        # was already configured.
        Rule("already-configured", rb"[\r\n]>\s*$",
             None, terminal=True, requires="connect-ftd"),
    ]


def erase_config_rules(answers):
    """Rules for the recovery flow: ``connect local-mgmt`` then
    ``erase configuration`` (the wizard guide notes it sometimes has to
    run twice, so the erase rules are allowed to re-fire)."""
    return [
        *_fxos_login_rules(answers),
        Rule("connect-local-mgmt", rb"[\r\n]firepower#\s*$",
             "connect local-mgmt", max_fires=1),
        Rule("erase", rb"\(local-mgmt\)#\s*$", "erase configuration",
             max_fires=3),
        Rule("confirm-erase",
             rb"are you sure\??[^\r\n]*\(yes/no\):?\s*$",
             "yes", max_fires=3),
        # Anchor to the shutdown broadcast, NOT the bare word "reboot":
        # the confirmation prompt itself says "...system will reboot.",
        # and on a second erase round (requires= already satisfied) a
        # chunk ending there must not be mistaken for the real reboot.
        Rule("rebooting", rb"going down for reboot", None, terminal=True,
             requires="confirm-erase"),
    ]
