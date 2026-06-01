"""Tests for console push serial prompt matching."""

import unittest

from netforge.serial_push import _SerialPushDialog


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
