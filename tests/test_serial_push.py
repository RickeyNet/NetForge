"""Tests for console push serial prompt matching."""

import unittest

from netforge.serial_push import _SerialPushDialog


class FakeCaptureSerial:
    """Serial stub for capture tests: a write triggers a scripted reply.

    ``replies`` maps a command substring to the bytes the 'device' streams
    back. ``b" "`` (the pager space) releases the next queued ``--More--``
    continuation supplied via ``more_parts``.
    """

    def __init__(self, replies, more_parts=None):
        self.replies    = replies
        self.more_parts = list(more_parts or [])
        self.buf        = bytearray()
        self.writes     = []

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, n):
        if not self.buf:
            return b""
        n = min(n, len(self.buf))
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def write(self, data):
        self.writes.append(data)
        if data == b" ":
            if self.more_parts:
                self.buf.extend(self.more_parts.pop(0))
            return
        text = data.decode("ascii", errors="replace").strip()
        for key, reply in self.replies.items():
            if key in text:
                self.buf.extend(reply)
                return


def _make_dialog(ser):
    """A _SerialPushDialog with just enough wired up to run a capture."""
    d = object.__new__(_SerialPushDialog)
    d._ser = ser
    d._stop_flag = False
    d._active_enable_pw = ""
    d._log = lambda *a, **k: None
    d._set_status = lambda *a, **k: None
    return d


class TestCapture(unittest.TestCase):
    def test_capture_strips_echo_and_prompt(self):
        ser = FakeCaptureSerial({
            "show version":
                b"show version\r\nCisco IOS Software, Version 15.2\r\n"
                b"uptime is 5 days\r\nSwitch#",
        })
        out = _make_dialog(ser)._capture("show version", idle_timeout=2)
        self.assertEqual(
            out, "Cisco IOS Software, Version 15.2\nuptime is 5 days")

    def test_capture_pages_through_more(self):
        # terminal length 0 didn't stick: the device paginates. The
        # capture must press space and stitch the continuation together.
        ser = FakeCaptureSerial(
            {"show running-config":
                b"show running-config\r\nline one\r\nline two\r\n --More--"},
            more_parts=[b"\r\nline three\r\nend\r\nSwitch#"])
        out = _make_dialog(ser)._capture("show running-config",
                                         idle_timeout=2)
        self.assertIn("line one", out)
        self.assertIn("line three", out)
        self.assertNotIn("--More--", out)
        self.assertIn(b" ", ser.writes)  # paged at least once

    def test_capture_idle_timeout_returns_partial(self):
        # A device that goes silent without a prompt must not hang forever.
        ser = FakeCaptureSerial({"show version": b"show version\r\npartial"})
        out = _make_dialog(ser)._capture("show version", idle_timeout=0.3)
        self.assertEqual(out, "partial")


class TestSerialPushPrompts(unittest.TestCase):
    def test_prompt_re_matches_hostname_prompt(self):
        buf = b"\r\nSwitch# "
        self.assertTrue(_SerialPushDialog._PROMPT_RE.search(buf))

    def test_prompt_re_matches_config_submode(self):
        buf = b"\r\nSwitch(config-if)# "
        self.assertTrue(_SerialPushDialog._PROMPT_RE.search(buf))

    def test_prompt_re_matches_user_mode(self):
        buf = b"Router>"
        self.assertTrue(_SerialPushDialog._PROMPT_RE.search(buf))

    def test_setup_re_matches_day_zero_dialog(self):
        buf = b"Would you like to enter the initial configuration dialog? [yes/no]:"
        self.assertTrue(_SerialPushDialog._SETUP_RE.search(buf))

    def test_pass_re_matches_enable_password_prompt(self):
        buf = b"Password: "
        self.assertTrue(_SerialPushDialog._PASS_RE.search(buf))


if __name__ == "__main__":
    unittest.main()
