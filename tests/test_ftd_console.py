"""Tests for the FTD day-0 console expect engine."""

import time
import unittest

from netforge.ftd.console import (
    ExpectSession,
    erase_config_rules,
    initial_setup_rules,
)


class FakeSerial:
    """Scripted serial port: each step is (output_bytes, expected_write).

    The next step's output is released once a write containing
    ``expected_write`` arrives. ``expected_write=None`` means the step is
    terminal (nothing more is expected).
    """

    def __init__(self, steps):
        self.steps  = list(steps)
        self.idx    = 0
        self.buf    = bytearray(self.steps[0][0]) if self.steps else bytearray()
        self.writes = []

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, n):
        if not self.buf:
            time.sleep(0.002)
            return b""
        n = min(n, len(self.buf))
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def write(self, data):
        self.writes.append(data)
        if self.idx >= len(self.steps):
            return
        expected = self.steps[self.idx][1]
        if expected is not None and expected in data:
            self.idx += 1
            if self.idx < len(self.steps):
                self.buf.extend(self.steps[self.idx][0])


ANSWERS = {
    "username":         "admin",
    "current_password": "Admin123",
    "new_password":     "S3cret!pw",
    "ip":               "10.20.30.40",
    "netmask":          "255.255.255.0",
    "gateway":          "10.20.30.1",
    "hostname":         "",
    "dns":              "",
    "search_domain":    "",
}


def _wizard_steps():
    return [
        (b"\r\nfirepower login: ",                                b"admin"),
        (b"\r\nPassword: ",                                       b"Admin123"),
        (b"\r\nYou are required to change your password."
         b"\r\nEnter new password: ",                             b"S3cret!pw"),
        (b"\r\nConfirm new password: ",                           b"S3cret!pw"),
        (b"\r\nfirepower# ",                                      b"connect ftd"),
        (b"\r\nYou must accept the EULA to continue."
         b"\r\nPress <ENTER> to display the EULA: ",              b"\r\n"),
        (b"\r\nEND USER LICENSE AGREEMENT ...\r\n--More--",       b" "),
        (b"\r\n...rest of the EULA...\r\nPlease enter 'YES' or "
         b"press <ENTER> to AGREE to the EULA: ",                 b"YES"),
        (b"\r\nDo you want to configure IPv4? (y/n) [y]: ",       b"y"),
        (b"\r\nDo you want to configure IPv6? (y/n) [n]: ",       b"n"),
        (b"\r\nConfigure IPv4 via DHCP or manually? "
         b"(dhcp/manual) [manual]: ",                             b"manual"),
        (b"\r\nEnter an IPv4 address for the management "
         b"interface [192.168.45.45]: ",                          b"10.20.30.40"),
        (b"\r\nEnter an IPv4 netmask for the management "
         b"interface [255.255.255.0]: ",                          b"255.255.255.0"),
        (b"\r\nEnter the IPv4 default gateway for the "
         b"management interface [192.168.45.1]: ",                b"10.20.30.1"),
        (b"\r\nEnter a fully qualified hostname for this "
         b"system [firepower]: ",                                 b"\r\n"),
        (b"\r\nEnter a comma-separated list of DNS servers "
         b"or 'none' [208.67.222.222]: ",                         b"\r\n"),
        (b"\r\nEnter a comma-separated list of search "
         b"domains or 'none' []: ",                               b"none"),
        (b"\r\nManage the device locally? (yes/no) [yes]: ",      b"yes"),
        (b"\r\nSuccessfully performed firstboot...\r\n> ",        None),
    ]


class TestInitialSetup(unittest.TestCase):
    def test_full_wizard(self):
        ser = FakeSerial(_wizard_steps())
        session = ExpectSession(ser, initial_setup_rules(ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "setup-complete")
        self.assertEqual(result.fired, [
            "login", "password", "new-pass", "confirm-pass",
            "connect-ftd", "eula-display", "eula-more", "eula-agree",
            "ipv4", "ipv6", "dhcp-manual", "mgmt-ip", "netmask",
            "gateway", "hostname", "dns", "search-domain",
            "manage-local", "setup-complete",
        ])

    def test_already_configured(self):
        steps = [
            (b"\r\nfirepower login: ", b"admin"),
            (b"\r\nPassword: ",        b"Admin123"),
            (b"\r\nfirepower# ",       b"connect ftd"),
            (b"\r\nConnecting to ftd console...\r\n> ", None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, initial_setup_rules(ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "already-configured")

    def test_timeout_reports_progress(self):
        steps = [
            (b"\r\nfirepower login: ", b"admin"),
            (b"\r\nPassword: ",        None),   # never answers further
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, initial_setup_rules(ANSWERS),
                                overall_timeout=1.0, idle_timeout=0.5,
                                nudge_interval=10)
        result = session.run()
        self.assertFalse(result.ok)
        self.assertIn("login", result.fired)


class TestEraseConfig(unittest.TestCase):
    def test_erase_flow(self):
        steps = [
            (b"\r\nfirepower login: ",                        b"admin"),
            (b"\r\nPassword: ",                               b"Admin123"),
            (b"\r\nfirepower# ",                              b"connect local-mgmt"),
            (b"\r\nfirepower(local-mgmt)# ",                  b"erase configuration"),
            (b"\r\nAll configurations will be erased and "
             b"system will reboot. Are you sure? (yes/no): ", b"yes"),
            (b"\r\nBroadcast message: The system is going "
             b"down for reboot NOW!\r\n",                     None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, erase_config_rules(ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "rebooting")

    def test_erase_needs_second_round(self):
        # The guide notes erase sometimes has to run twice; the second
        # round must work end to end.
        steps = [
            (b"\r\nfirepower login: ",                        b"admin"),
            (b"\r\nPassword: ",                               b"Admin123"),
            (b"\r\nfirepower# ",                              b"connect local-mgmt"),
            (b"\r\nfirepower(local-mgmt)# ",                  b"erase configuration"),
            (b"\r\nAll configurations will be erased and "
             b"system will reboot. Are you sure? (yes/no): ", b"yes"),
            (b"\r\nfirepower(local-mgmt)# ",                  b"erase configuration"),
            (b"\r\nAll configurations will be erased and "
             b"system will reboot. Are you sure? (yes/no): ", b"yes"),
            (b"\r\nBroadcast message: The system is going "
             b"down for reboot NOW!\r\n",                     None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, erase_config_rules(ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "rebooting")
        self.assertEqual(result.fired.count("erase"), 2)

    def test_round_two_prompt_is_not_mistaken_for_reboot(self):
        # Regression: a round-2 confirmation prompt that arrives
        # chunk-split right after '...system will reboot.' must NOT
        # satisfy the terminal 'rebooting' rule (requires=confirm-erase
        # is already met from round 1).
        steps = [
            (b"\r\nfirepower login: ",                        b"admin"),
            (b"\r\nPassword: ",                               b"Admin123"),
            (b"\r\nfirepower# ",                              b"connect local-mgmt"),
            (b"\r\nfirepower(local-mgmt)# ",                  b"erase configuration"),
            (b"\r\nAll configurations will be erased and "
             b"system will reboot. Are you sure? (yes/no): ", b"yes"),
            (b"\r\nfirepower(local-mgmt)# ",                  b"erase configuration"),
            # Chunk ends mid-prompt, right after the word "reboot."
            (b"\r\nAll configurations will be erased and "
             b"system will reboot.",                          None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, erase_config_rules(ANSWERS),
                                overall_timeout=5, idle_timeout=0.4)
        result = session.run()
        self.assertFalse(result.ok)
        self.assertNotIn("rebooting", result.fired)


if __name__ == "__main__":
    unittest.main()
