"""Detect and collect device-rejected commands during a config push.

Shared by the IOS console push (netforge/serial_push.py) and the FTD
console push (netforge/ftd/dialog.py) so both can show a consolidated
summary of what the device complained about instead of leaving the
failures buried in a long scrolling transcript.
"""

import re

# IOS prints command errors/warnings as a line beginning with '%', e.g.
#   % Invalid input detected at '^' marker.
#   % Incomplete command.
#   % Ambiguous command:  "sh ip"
# In the response captured right after a single pushed line, a '%' line is
# essentially always the device reacting to that line, so we can attribute
# it to the exact command that was sent.
_IOS_ERROR_RE = re.compile(r"^\s*%\s*\S")

# FTD/FXOS surface errors differently and the console also streams a lot of
# benign text (EULA, banners) that can contain '%', so match only explicit
# error markers here rather than any '%' line.
FTD_ERROR_RE = re.compile(
    r"\bERROR:|%\s*Invalid|%\s*Incomplete|%\s*Ambiguous|"
    r"\bInvalid input\b|\bcommand not found\b",
    re.IGNORECASE)


def _split_lines(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def scan_ios_errors(response):
    """Return the error/warning lines ('%' lines) in one command's reply."""
    return [ln.strip() for ln in _split_lines(response)
            if _IOS_ERROR_RE.match(ln)]


class PushErrorLog:
    """Collects per-command errors and formats a summary at the end."""

    def __init__(self):
        self.items = []  # list of (line_no | None, command, message)

    def add(self, command, message, line_no=None):
        self.items.append((line_no, command, message))

    def add_ios(self, line_no, command, response):
        """Scan a single command's device reply and record any errors."""
        for msg in scan_ios_errors(response):
            self.add(command, msg, line_no)

    def __bool__(self):
        return bool(self.items)

    def __len__(self):
        return len(self.items)

    def summary(self, title="Lines flagged by the device (errors/warnings)"):
        if not self.items:
            return ""
        out = [f"=== {title}: {len(self.items)} ===" ]
        for line_no, command, message in self.items:
            loc = f"line {line_no}: " if line_no else ""
            out.append(f"  {loc}{command}")
            out.append(f"      -> {message}")
        return "\n".join(out)


class LineErrorScanner:
    """Scan streamed text for error lines, robust to chunk boundaries.

    Console output arrives in arbitrary chunks, so an error marker can be
    split across two reads. Hold back the partial last line until the next
    feed (or ``flush``) so a marker is never missed or double-counted.
    """

    def __init__(self, pattern=FTD_ERROR_RE):
        self._re = pattern
        self._carry = ""
        self.errors = []

    def feed(self, text):
        if not text:
            return
        parts = _split_lines(self._carry + text)
        self._carry = parts.pop()  # last element is the incomplete line
        for ln in parts:
            if self._re.search(ln):
                self.errors.append(ln.strip())

    def flush(self):
        if self._carry and self._re.search(self._carry):
            self.errors.append(self._carry.strip())
        self._carry = ""

    def summary(self, title="Errors seen on the console"):
        if not self.errors:
            return ""
        out = [f"=== {title}: {len(self.errors)} ==="]
        out.extend(f"  {e}" for e in self.errors)
        return "\n".join(out)
