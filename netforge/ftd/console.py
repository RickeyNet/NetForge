"""FTD console automation: pre-stage day-0 wizard and pre-ship config.

Drives the interactive prompts that Cisco Firepower appliances present on
the console port with a small expect-style rule engine over a serial port.
Pre-stage covers the first-boot wizard (FXOS login, forced password change,
``connect ftd``, EULA, management network, "manage locally"); pre-ship
covers the steps run once customer site info is known (FMC manager
registration, management-data-interface wizard, management0 tweaks) plus a
show-command capture. The engine is UI-free and only needs a pyserial-like
object (read / write / in_waiting), so it can be unit-tested with a fake
port.
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
# Pre-ship is mostly quick prompt/answer, but applying the
# management-data-interface config can keep the console quiet for a
# couple of minutes while the data plane reconfigures.
PRESHIP_TIMEOUT      = 1200.0
PRESHIP_IDLE_TIMEOUT = 300.0

# Show commands captured for the pre-ship config record, in order.
PRESHIP_CAPTURE_CMDS = (
    "show managers",
    "show network",
    "show startup-config | include rout",
    "show version",
)


class Rule:
    """When *pattern* matches the unconsumed tail of the buffer, respond.

    ``response`` may be:
      str   -> sent followed by a bare CR (what Enter sends in a terminal
               emulator); "" sends just the CR, i.e. "accept the default"
               for wizard questions. Never CR+LF: the appliance console is
               a Linux tty that maps CR to NL, so CR+LF arrives as TWO
               line endings and the stray empty line desyncs paired
               prompts (new password / confirm never match).
      bytes -> sent raw, no line ending (e.g. b" " to page the EULA)
      None  -> nothing is sent; used for terminal "we're done" rules
    ``requires`` names another rule that must already have fired before
    this one becomes eligible - it keeps generic patterns (like a bare
    ``>`` prompt) from matching too early.
    ``fail`` marks a terminal rule as a failure outcome (e.g. the device
    rejected a command), so the session ends with ok=False instead of
    reporting success.
    """

    def __init__(self, name, pattern, response, max_fires=3,
                 terminal=False, requires=None, fail=False):
        self.name      = name
        self.pattern   = re.compile(pattern, re.IGNORECASE)
        self.response  = response
        self.max_fires = max_fires
        self.terminal  = terminal
        self.requires  = requires
        self.fail      = fail
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
    matched yet the session periodically nudges the console with a CR to
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
                    self.ser.write(b"\r")
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
                return ExpectResult(not rule.fail, rule.name, self.fired)

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
            rule.response.encode("ascii", errors="replace") + b"\r")
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
        # The lookbehind keeps this from ever answering an
        # "Enter/Confirm new password:" prompt with the *current*
        # password once new-pass / confirm-pass run out of fires.
        Rule("password", rb"(?<!new )password:\s*$",
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
        # "list of" pins these to the wizard prompts; the applying phase
        # prints status lines like "Setting DNS servers:" that would
        # otherwise fire the rule and inject a junk input line.
        Rule("dns", rb"list of DNS servers[^\r\n]*:\s*$",
             a.get("dns", "")),
        Rule("search-domain",
             rb"list of search domains[^\r\n]*:\s*$",
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


def _ftd_shell_rules(a):
    """Login + drop into the FTD CLI; shared by the pre-ship flows.

    Unlike the day-0 flow the FXOS hostname may no longer be the factory
    ``firepower``, so the supervisor prompt accepts any hostname.
    """
    return [
        *_fxos_login_rules(a),
        Rule("connect-ftd", rb"[\r\n][\w.\-]+#\s*$", "connect ftd",
             max_fires=1),
    ]


def preship_rules(answers):
    """Rules for the pre-ship flow, run once customer site info is known.

    ``answers`` keys: username, current_password, new_password (the
    login password again - no password change is expected here), fmc_ip,
    reg_key, and for the management-data-interface wizard (when
    ``use_data_mgmt``): data_iface, iface_name, ip, netmask, gateway,
    dns, ddns. ``disable_mgmt`` adds the management0 disable step (do
    not use for HA); ``dedicated_mgmt`` adds the static management0
    config used on 2100/3100 series (mgmt_ip / mgmt_netmask /
    mgmt_gateway).

    Commands are dispatched in sequence off the ``>`` prompt: each
    ``>``-pattern rule fires once and gates the next via ``requires``.
    """
    a = answers
    use_data_mgmt = a.get("use_data_mgmt", True)
    rules = [
        *_ftd_shell_rules(a),
        # First '>' prompt -> register the FMC manager. No requires:
        # a console session left sitting in the FTD CLI skips login.
        Rule("mgr-add", rb"[\r\n]>\s*$",
             f"configure manager add {a['fmc_ip']} {a['reg_key']}",
             max_fires=1),
    ]
    if use_data_mgmt:
        # Listed ahead of mgr-confirm on purpose: mgr-confirm usually has
        # fires left during the management-data-interface wizard, and if
        # a build phrases this destructive confirm with "(yes/no)" the
        # generic yes/no pattern would answer YES and wipe the device
        # config. requires="mdi-start" keeps it inert until the wizard.
        rules.append(
            Rule("mdi-clear",
                 rb"clear all the device configuration[^\r\n]*:\s*$",
                 "n", requires="mdi-start"))
    rules += [
        # Answer the yes/no confirmation(s) that follow the add. When the
        # device is already managed (a previous / local manager), the add
        # first prompts to delete it before registering - that prompt uses
        # square brackets ([yes/no]) rather than the parentheses or
        # 'YES' or 'NO' of the registration confirm, so match every style.
        # max_fires covers a delete confirm plus the registration confirm.
        Rule("mgr-confirm",
             rb"(?:'YES' or 'NO'|[\[(]\s*yes\s*/\s*no\s*[\])])"
             rb"[^\r\n]*:?\s*$",
             "YES", max_fires=3, requires="mgr-add"),
        # Some versions warn before reconfiguring the management path.
        Rule("continue-y",
             rb"do you (?:wish|want) to continue[^\r\n]*:\s*$", "y",
             max_fires=3, requires="mgr-add"),
    ]
    prev = "mgr-add"
    if use_data_mgmt:
        rules += [
            Rule("mdi-start", rb"[\r\n]>\s*$",
                 "configure network management-data-interface",
                 max_fires=1, requires=prev),
            Rule("data-iface",
                 rb"data interface to use for management[^\r\n]*:\s*$",
                 a["data_iface"], requires="mdi-start"),
            Rule("iface-name", rb"name for the interface[^\r\n]*:\s*$",
                 a["iface_name"], requires="mdi-start"),
            # Must outrank mdi-ip: the method prompt also says "address".
            Rule("dhcp-manual",
                 rb"\((?:dhcp ?/ ?manual|manual ?/ ?dhcp)\)[^\r\n]*:\s*$",
                 "manual", requires="mdi-start"),
            Rule("mdi-ip", rb"address[^\r\n]*:\s*$", a["ip"],
                 requires="mdi-start"),
            Rule("mdi-netmask", rb"netmask[^\r\n]*:\s*$", a["netmask"],
                 requires="mdi-start"),
            Rule("mdi-gateway", rb"gateway[^\r\n]*:\s*$", a["gateway"],
                 requires="mdi-start"),
            # DDNS before DNS: "DDNS server update URL" contains the
            # substring "DNS server" and would satisfy the DNS rule.
            Rule("mdi-ddns", rb"DDNS[^\r\n]*:\s*$",
                 a.get("ddns") or "none", requires="mdi-start"),
            Rule("mdi-dns", rb"DNS server[^\r\n]*:\s*$",
                 a.get("dns") or "0.0.0.0", requires="mdi-start"),
            # mdi-clear lives above mgr-confirm - see comment there.
        ]
        prev = "mdi-start"
    if a.get("disable_mgmt"):
        rules.append(
            Rule("disable-mgmt0", rb"[\r\n]>\s*$",
                 "configure network management-interface disable "
                 "management0",
                 max_fires=1, requires=prev))
        prev = "disable-mgmt0"
    if a.get("dedicated_mgmt"):
        rules.append(
            Rule("mgmt0-ipv4", rb"[\r\n]>\s*$",
                 f"configure network ipv4 manual {a['mgmt_ip']} "
                 f"{a['mgmt_netmask']} {a['mgmt_gateway']} management0",
                 max_fires=1, requires=prev))
        prev = "mgmt0-ipv4"
    rules.append(Rule("preship-complete", rb"[\r\n]>\s*$", None,
                      terminal=True, requires=prev))
    return rules


def capture_login_rules(answers):
    """Just get to the FTD ``>`` prompt (capture-only pre-ship runs)."""
    return [
        *_ftd_shell_rules(answers),
        Rule("ftd-cli", rb"[\r\n]>\s*$", None, terminal=True),
    ]


def regenerate_cert_rules(answers):
    """Rules to regenerate expired internal keyring certificate(s).

    Fixes the FDM-managed upgrade failure (Cisco bug CSCwd11825): when
    the device's internal HTTPS / web-server certificate has expired the
    software upgrade aborts with "The chosen certificate has already
    expired. Please apply an unexpired certificate." Regenerating the
    keyring from the FTD CLI takes effect immediately and needs no
    deployment - unlike replacing the certificate in FDM, whose
    deployment is itself blocked by the expired cert (the deploy loop).

    ``answers`` keys: username, current_password, new_password (login
    only - no password change is expected here), and ``keyrings``, a
    list of keyring names to regenerate in order, each "fdm" (the FDM
    web-server cert) or "default" (the FXOS management cert).

    Each command is dispatched off the ``>`` prompt and gated to the
    previous one via ``requires``; a tolerant confirm rule answers the
    "are you sure / continue" prompt that some builds show and others
    skip.
    """
    a = answers
    keyrings = a.get("keyrings") or ["fdm"]
    # A command rejection followed by the '>' prompt. Matching the prompt
    # too (not just the error text) matters twice over: a fire consumes
    # the scan window, so firing on the bare error would swallow a
    # same-chunk prompt and strand the session; and it guarantees the
    # device is ready to read the fallback command.
    rejected = (rb"(?:syntax error|illegal command|invalid command)"
                rb"[\s\S]*?[\r\n]>\s*$")
    rules = [
        *_ftd_shell_rules(a),
        # Even the bare fallback command was rejected - this build does
        # not have the command at all; end the run as a failure.
        Rule("regen-failed", rejected, None, terminal=True, fail=True,
             requires="regen-fallback"),
        # Some builds take no keyring argument (e.g. 7.0.1 accepts only
        # a bare <cr>): when the argument form is rejected, re-run the
        # command bare. Remaining keyrings are skipped afterwards - a
        # no-argument build only has the one keyring to regenerate.
        Rule("regen-fallback", rejected,
             "system support regenerate-security-keyring",
             max_fires=1, requires="regen-0"),
        Rule("regen-fallback-done", rb"[\r\n]>\s*$", None, terminal=True,
             requires="regen-fallback"),
        # Some builds prompt to confirm; others regenerate silently.
        Rule("regen-confirm",
             rb"(?:\(yes/no\)|continue\??)[^\r\n]*:?\s*$", "yes",
             max_fires=len(keyrings) * 2, requires="regen-0"),
    ]
    prev = None  # first command fires on the first '>' (requires=None)
    for i, keyring in enumerate(keyrings):
        name = f"regen-{i}"
        rules.append(
            Rule(name, rb"[\r\n]>\s*$",
                 f"system support regenerate-security-keyring {keyring}",
                 max_fires=1, requires=prev))
        prev = name
    rules.append(Rule("regen-complete", rb"[\r\n]>\s*$", None,
                      terminal=True, requires=prev))
    return rules


# ---------------------------------------------------------------------------
# Show-command capture (runs after an ExpectSession left us at '>')
# ---------------------------------------------------------------------------
_FTD_PROMPT_RE = re.compile(rb"[\r\n]>\s*$")
_MORE_RE       = re.compile(rb"--More--\s*$")


def capture_command(ser, cmd, log=None, stop=None, timeout=60.0,
                    quiet=0.4):
    """Run one CLISH command at the FTD ``>`` prompt, return its output.

    Pages through ``--More--`` prompts, then waits for the trailing
    ``>`` plus a short quiet grace period before returning. The echoed
    command, pager artifacts, and the trailing prompt are stripped so
    the result is just the command's output.
    """
    log  = log or (lambda _msg: None)
    stop = stop or (lambda: False)
    ser.write(cmd.encode("ascii", errors="replace") + b"\r")
    buf         = bytearray()
    deadline    = time.monotonic() + timeout
    quiet_until = None
    while time.monotonic() < deadline and not stop():
        chunk = ser.read(getattr(ser, "in_waiting", 0) or 1)
        if chunk:
            buf.extend(chunk)
            log(chunk.decode("utf-8", errors="replace"))
            tail = bytes(buf[-200:])
            if _MORE_RE.search(tail):
                ser.write(b" ")
                quiet_until = None
            elif _FTD_PROMPT_RE.search(tail):
                quiet_until = time.monotonic() + quiet
            else:
                quiet_until = None
        else:
            if quiet_until is not None and time.monotonic() >= quiet_until:
                break
            time.sleep(0.01)
    return _clean_capture(cmd, buf.decode("utf-8", errors="replace"))


def _clean_capture(cmd, text):
    """Strip the echoed command, pager noise, and the trailing prompt."""
    text  = text.replace("--More--", "")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and cmd in lines[0]:
        lines = lines[1:]
    while lines and lines[-1].strip() in ("", ">"):
        lines.pop()
    return "\n".join(lines).strip("\n")


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
