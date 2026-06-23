"""Tests for push error detection and summary collection."""

import unittest

from netforge.push_errors import (
    LineErrorScanner,
    PushErrorLog,
    scan_ios_errors,
)


class TestIosErrorScan(unittest.TestCase):
    def test_detects_invalid_input(self):
        resp = ("interface Gi1/0/1\r\n"
                "swithcport mode access\r\n"
                "                ^\r\n"
                "% Invalid input detected at '^' marker.\r\n"
                "Switch(config-if)#")
        errs = scan_ios_errors(resp)
        self.assertEqual(errs, ["% Invalid input detected at '^' marker."])

    def test_clean_response_has_no_errors(self):
        resp = ("interface Gi1/0/1\r\n"
                "Switch(config-if)#")
        self.assertEqual(scan_ios_errors(resp), [])

    def test_multiple_markers(self):
        resp = "% Incomplete command.\r\n% Ambiguous command:  \"sh\"\r\n#"
        self.assertEqual(len(scan_ios_errors(resp)), 2)


class TestPushErrorLog(unittest.TestCase):
    def test_collects_and_summarizes_with_line_numbers(self):
        log = PushErrorLog()
        log.add_ios(12, "swithcport mode access",
                    "% Invalid input detected at '^' marker.\nSwitch#")
        log.add_ios(20, "ip addr 1.1.1.1", "% Incomplete command.\nSwitch#")
        self.assertTrue(log)
        self.assertEqual(len(log), 2)
        summary = log.summary()
        self.assertIn("line 12: swithcport mode access", summary)
        self.assertIn("% Invalid input", summary)
        self.assertIn("line 20: ip addr 1.1.1.1", summary)

    def test_empty_log_is_falsey_and_blank(self):
        log = PushErrorLog()
        self.assertFalse(log)
        self.assertEqual(log.summary(), "")


class TestLineErrorScanner(unittest.TestCase):
    def test_catches_marker_split_across_feeds(self):
        s = LineErrorScanner()
        # "ERROR: manager add failed" arrives split across two reads.
        s.feed("configure manager add ...\r\nERR")
        s.feed("OR: manager add failed\r\n> ")
        s.flush()
        self.assertEqual(s.errors, ["ERROR: manager add failed"])

    def test_ignores_benign_percent_text(self):
        s = LineErrorScanner()
        s.feed("Upgrade is 5% complete\r\n")
        s.feed("EULA: 100% reviewed\r\n")
        s.flush()
        self.assertEqual(s.errors, [])

    def test_flush_emits_trailing_partial_line(self):
        s = LineErrorScanner()
        s.feed("ERROR: no newline yet")  # never terminated by \n
        self.assertEqual(s.errors, [])   # held back until flush
        s.flush()
        self.assertEqual(s.errors, ["ERROR: no newline yet"])


if __name__ == "__main__":
    unittest.main()
