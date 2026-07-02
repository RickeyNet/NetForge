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


class FakeLineSerial:
    """Serial stub for _send_line: a written command triggers a reply.

    ``pw_triggers`` is a set of command substrings that make the device
    answer with a ``Password:`` prompt first; the next write (the password
    answer) then releases the normal device prompt. ``max_chunk`` caps how
    many bytes one read returns, mimicking a real console where bytes
    trickle in rather than arriving as one atomic reply. ``pw_rejects``
    makes the device reject that many password answers with a fresh
    ``Password:`` prompt (a wrong enable password).
    """

    def __init__(self, prompt=b"\r\nSwitch(config)# ", pw_triggers=(),
                 max_chunk=None, pw_rejects=0):
        self.prompt      = prompt
        self.pw_triggers = set(pw_triggers)
        self.max_chunk   = max_chunk
        self.pw_rejects  = pw_rejects
        self.buf         = bytearray()
        self.writes      = []
        self._await_pw   = False

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, n):
        if not self.buf:
            return b""
        n = min(n, len(self.buf))
        if self.max_chunk:
            n = min(n, self.max_chunk)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def write(self, data):
        self.writes.append(data)
        if self._await_pw:
            # This write is the answer to the password prompt.
            if self.pw_rejects:
                self.pw_rejects -= 1
                self.buf.extend(b"\r\nPassword: ")
                return
            self._await_pw = False
            self.buf.extend(self.prompt)
            return
        text = data.decode("ascii", errors="replace").strip()
        if any(t in text for t in self.pw_triggers):
            self._await_pw = True
            self.buf.extend(b"\r\nPassword: ")
            return
        self.buf.extend(self.prompt)


class TestSendLinePasswordPrompt(unittest.TestCase):
    def test_answers_password_prompt_midpush(self):
        # A config line causes the switch to drop to a Password: prompt;
        # the push must send the enable password, not the next line.
        ser = FakeLineSerial(pw_triggers=("line con 0",))
        d = _make_dialog(ser)
        d._active_enable_pw = "s3cret"
        resp = d._send_line("line con 0", expect_prompt=True, timeout=2)
        self.assertIn(b"line con 0\r\n", ser.writes)
        self.assertIn(b"s3cret\r\n", ser.writes)
        # The enable password must be sent AFTER the command, in response
        # to the prompt - never before it.
        self.assertLess(ser.writes.index(b"line con 0\r\n"),
                        ser.writes.index(b"s3cret\r\n"))
        self.assertIn(b"Switch(config)# ", resp)

    def test_password_sent_once_when_reply_trickles(self):
        # Bytes arrive one at a time, as on a real 9600-baud console. After
        # the password is answered the buffer still ends with 'Password:',
        # and the CRLF that precedes the returning prompt arrives as its
        # own chunk - \s* in _PASS_RE soaks it up, so without the scan
        # offset the stale prompt re-matches and the password is sent a
        # second time (which then runs as a bogus command at the prompt).
        ser = FakeLineSerial(pw_triggers=("line con 0",), max_chunk=1)
        d = _make_dialog(ser)
        d._active_enable_pw = "s3cret"
        resp = d._send_line("line con 0", expect_prompt=True, timeout=2)
        self.assertEqual(ser.writes.count(b"s3cret\r\n"), 1)
        # Byte-at-a-time reads return the instant '#' lands, so the
        # trailing space may not have arrived yet.
        self.assertIn(b"Switch(config)#", resp)

    def test_wrong_password_capped_at_two_attempts(self):
        # A rejected password (device re-prompts) gets exactly one retry;
        # after that the loop stops answering so a wrong enable password
        # can't ping-pong with the device until the config runs dry.
        ser = FakeLineSerial(pw_triggers=("line con 0",), pw_rejects=5)
        d = _make_dialog(ser)
        d._active_enable_pw = "wr0ng"
        d._send_line("line con 0", expect_prompt=True, timeout=0.4)
        self.assertEqual(ser.writes.count(b"wr0ng\r\n"), 2)

    def test_no_password_sent_without_prompt(self):
        # A normal line that returns straight to the prompt must not emit
        # the enable password.
        ser = FakeLineSerial()
        d = _make_dialog(ser)
        d._active_enable_pw = "s3cret"
        d._send_line("hostname SW1", expect_prompt=True, timeout=2)
        self.assertNotIn(b"s3cret\r\n", ser.writes)

    def test_empty_enable_pw_not_injected_midpush(self):
        # With no enable password configured, a stray Password:-looking
        # tail must not cause a blank/enable write to be injected.
        ser = FakeLineSerial(pw_triggers=("banner",))
        d = _make_dialog(ser)
        d._active_enable_pw = ""
        d._send_line("banner motd x", expect_prompt=True, timeout=0.6)
        # Only the command itself should have been written.
        self.assertEqual(ser.writes, [b"banner motd x\r\n"])


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
