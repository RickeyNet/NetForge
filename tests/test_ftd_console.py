"""Tests for the FTD day-0 console expect engine."""

import time
import unittest

from netforge.ftd.console import (
    ExpectSession,
    capture_command,
    capture_login_rules,
    erase_config_rules,
    initial_setup_rules,
    preship_rules,
    regenerate_cert_rules,
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


PRESHIP_ANSWERS = {
    "username":         "admin",
    "current_password": "S3cret!pw",
    "new_password":     "S3cret!pw",
    "fmc_ip":           "198.51.100.10",
    "reg_key":          "cisco123",
    "use_data_mgmt":    True,
    "data_iface":       "Ethernet1/1",
    "iface_name":       "outside",
    "ip":               "203.0.113.2",
    "netmask":          "255.255.255.252",
    "gateway":          "203.0.113.1",
    "dns":              "0.0.0.0",
    "ddns":             "none",
    "disable_mgmt":     True,
    "dedicated_mgmt":   False,
    "mgmt_ip":          "",
    "mgmt_netmask":     "",
    "mgmt_gateway":     "",
}


class TestPreship(unittest.TestCase):
    def test_full_preship_flow(self):
        steps = [
            (b"\r\nfirepower login: ",  b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nfirepower# ",        b"connect ftd"),
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nIf you proceed the manager will be set."
             b"\r\nPlease enter 'YES' or 'NO': ",                 b"YES"),
            (b"\r\nManager successfully configured.\r\n> ",
             b"configure network management-data-interface"),
            (b"\r\nData interface to use for management: ",
             b"Ethernet1/1"),
            (b"\r\nSpecify a name for the interface [outside]: ",
             b"outside"),
            (b"\r\nIP address (manual / dhcp) [dhcp]: ",          b"manual"),
            (b"\r\nIPv4/IPv6 address: ",                          b"203.0.113.2"),
            (b"\r\nNetmask/IPv6 prefix: ",
             b"255.255.255.252"),
            (b"\r\nDefault Gateway: ",                            b"203.0.113.1"),
            (b"\r\nComma-separated list of DNS servers [none]: ",
             b"0.0.0.0"),
            (b"\r\nDDNS server update URL [none]: ",              b"none"),
            (b"\r\nDo you wish to clear all the device "
             b"configuration before applying ? (y/n) [n]: ",      b"n"),
            (b"\r\nConfiguration done with option to allow "
             b"manager access from any network\r\n> ",
             b"configure network management-interface disable "
             b"management0"),
            (b"\r\nConfiguration updated successfully\r\n> ",     None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(PRESHIP_ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "preship-complete")
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd", "mgr-add",
            "mgr-confirm", "mdi-start", "data-iface", "iface-name",
            "dhcp-manual", "mdi-ip", "mdi-netmask", "mdi-gateway",
            "mdi-dns", "mdi-ddns", "mdi-clear", "disable-mgmt0",
            "preship-complete",
        ])

    def test_delete_previous_manager_confirm(self):
        # When the device is already managed (a previous / local manager),
        # `configure manager add` first prompts to delete it before
        # registering. That confirm uses square brackets ([yes/no]) and
        # must be answered so the flow reaches the registration confirm.
        a = dict(PRESHIP_ANSWERS, use_data_mgmt=False, disable_mgmt=False,
                 dedicated_mgmt=False)
        steps = [
            (b"\r\nfirepower login: ",  b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nfirepower# ",        b"connect ftd"),
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nA manager is already configured on this device."
             b"\r\nContinuing will delete the current manager."
             b"\r\nDo you want to continue? [yes/no]: ",          b"YES"),
            (b"\r\nManager deleted. Registering new manager."
             b"\r\nPlease enter 'YES' or 'NO': ",                 b"YES"),
            (b"\r\nManager successfully configured.\r\n> ",       None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "preship-complete")
        self.assertEqual(result.fired.count("mgr-confirm"), 2)
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd", "mgr-add",
            "mgr-confirm", "mgr-confirm", "preship-complete"])

    def test_yesno_clear_prompt_not_hijacked_by_mgr_confirm(self):
        # Regression for rule ordering: if a build phrases the destructive
        # "clear all the device configuration" confirm with "(yes/no)"
        # instead of "(y/n)", it matches mgr-confirm's generic yes/no
        # pattern too. mdi-clear must outrank it and answer "n" - a "YES"
        # here wipes the device config.
        a = dict(PRESHIP_ANSWERS, disable_mgmt=False)
        steps = [
            (b"\r\nfirepower login: ",  b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nfirepower# ",        b"connect ftd"),
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nPlease enter 'YES' or 'NO': ",                 b"YES"),
            (b"\r\nManager successfully configured.\r\n> ",
             b"configure network management-data-interface"),
            (b"\r\nDo you wish to clear all the device "
             b"configuration before applying ? (yes/no) [n]: ",   b"n"),
            (b"\r\nConfiguration done\r\n> ",                     None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertNotIn(b"YES\r\n", ser.writes[-2:])
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd", "mgr-add",
            "mgr-confirm", "mdi-start", "mdi-clear", "preship-complete"])

    def test_want_to_continue_without_brackets_answered(self):
        # The reconfigure warning on some builds says "Do you want to
        # continue?" with no (yes/no) hint at all - continue-y must catch
        # it ("wish" and "want" phrasings both exist in the wild).
        a = dict(PRESHIP_ANSWERS, use_data_mgmt=False, disable_mgmt=False,
                 dedicated_mgmt=False)
        steps = [
            (b"\r\nfirepower login: ",  b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nfirepower# ",        b"connect ftd"),
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nThis will reconfigure the management path."
             b"\r\nDo you want to continue?: ",                   b"y"),
            (b"\r\nManager successfully configured.\r\n> ",       None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd", "mgr-add",
            "continue-y", "preship-complete"])

    def test_dedicated_mgmt_only(self):
        # HA-style run: no management-data-interface, configure
        # management0 statically instead (2100/3100 procedure).
        a = dict(PRESHIP_ANSWERS,
                 use_data_mgmt=False, disable_mgmt=False,
                 dedicated_mgmt=True,
                 mgmt_ip="10.9.8.7", mgmt_netmask="255.255.255.0",
                 mgmt_gateway="10.9.8.1")
        steps = [
            (b"\r\nfirepower login: ",  b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nfirepower# ",        b"connect ftd"),
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nManager successfully configured.\r\n> ",
             b"configure network ipv4 manual 10.9.8.7 255.255.255.0 "
             b"10.9.8.1 management0"),
            (b"\r\nConfiguration updated successfully\r\n> ",     None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "preship-complete")
        self.assertIn("mgmt0-ipv4", result.fired)
        self.assertNotIn("mdi-start", result.fired)

    def test_renamed_fxos_prompt_still_connects(self):
        # Pre-stage may have set a hostname; the supervisor prompt is
        # no longer the factory "firepower#".
        steps = [
            (b"\r\nNYC-FW01 login: ",   b"admin"),
            (b"\r\nPassword: ",         b"S3cret!pw"),
            (b"\r\nNYC-FW01# ",         b"connect ftd"),
            (b"\r\n> ",                 None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, capture_login_rules(PRESHIP_ANSWERS),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "ftd-cli")

    def test_session_already_at_ftd_cli(self):
        # A console left sitting in the FTD CLI answers the nudge with
        # the '>' prompt; login is skipped entirely.
        steps = [
            (b"\r\n> ",
             b"configure manager add 198.51.100.10 cisco123"),
            (b"\r\nManager successfully configured.\r\n> ",
             b"configure network management-interface disable "
             b"management0"),
            (b"\r\nConfiguration updated successfully\r\n> ",     None),
        ]
        a = dict(PRESHIP_ANSWERS, use_data_mgmt=False)
        ser = FakeSerial(steps)
        session = ExpectSession(ser, preship_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.fired, [
            "mgr-add", "disable-mgmt0", "preship-complete"])


class TestRegenerateCert(unittest.TestCase):
    LOGIN = {"username": "admin", "current_password": "S3cret!pw",
             "new_password": "S3cret!pw"}

    def test_fdm_keyring_with_confirm(self):
        a = dict(self.LOGIN, keyrings=["fdm"])
        steps = [
            (b"\r\nfirepower login: ", b"admin"),
            (b"\r\nPassword: ",        b"S3cret!pw"),
            (b"\r\nfirepower# ",       b"connect ftd"),
            (b"\r\n> ",
             b"system support regenerate-security-keyring fdm"),
            (b"\r\nThis regenerates the fdm keyring certificate."
             b"\r\nDo you want to continue? (yes/no): ",          b"yes"),
            (b"\r\nKeyring certificate regenerated.\r\n> ",       None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, regenerate_cert_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.reason, "regen-complete")
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd",
            "regen-0", "regen-confirm", "regen-complete"])

    def test_silent_regen_no_confirm(self):
        # Builds that regenerate without a confirmation prompt still
        # complete (the confirm rule simply never fires).
        a = dict(self.LOGIN, keyrings=["fdm"])
        steps = [
            (b"\r\nfirepower login: ", b"admin"),
            (b"\r\nPassword: ",        b"S3cret!pw"),
            (b"\r\nfirepower# ",       b"connect ftd"),
            (b"\r\n> ",
             b"system support regenerate-security-keyring fdm"),
            (b"\r\nKeyring certificate regenerated.\r\n> ",       None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, regenerate_cert_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd",
            "regen-0", "regen-complete"])

    def test_both_keyrings_in_order(self):
        a = dict(self.LOGIN, keyrings=["default", "fdm"])
        steps = [
            (b"\r\nfirepower login: ", b"admin"),
            (b"\r\nPassword: ",        b"S3cret!pw"),
            (b"\r\nfirepower# ",       b"connect ftd"),
            (b"\r\n> ",
             b"system support regenerate-security-keyring default"),
            (b"\r\nDefault keyring regenerated.\r\n> ",
             b"system support regenerate-security-keyring fdm"),
            (b"\r\nFDM keyring regenerated.\r\n> ",               None),
        ]
        ser = FakeSerial(steps)
        session = ExpectSession(ser, regenerate_cert_rules(a),
                                overall_timeout=10, idle_timeout=2)
        result = session.run()
        self.assertTrue(result.ok, msg=f"{result!r} fired={result.fired}")
        self.assertEqual(result.fired, [
            "login", "password", "connect-ftd",
            "regen-0", "regen-1", "regen-complete"])


class TestCaptureCommand(unittest.TestCase):
    def test_strips_echo_and_prompt(self):
        ser = FakeSerial([
            (b"", b"show managers"),
            (b"show managers\r\n"
             b"Host                      : 198.51.100.10\r\n"
             b"Registration              : pending\r\n"
             b"> ",                                               None),
        ])
        out = capture_command(ser, "show managers", timeout=5, quiet=0.05)
        self.assertEqual(out,
                         "Host                      : 198.51.100.10\n"
                         "Registration              : pending")

    def test_pages_through_more(self):
        ser = FakeSerial([
            (b"", b"show version"),
            (b"show version\r\nline one\r\n--More--",             b" "),
            (b"\r\nline two\r\n> ",                               None),
        ])
        out = capture_command(ser, "show version", timeout=5, quiet=0.05)
        self.assertEqual(out, "line one\n\nline two")


if __name__ == "__main__":
    unittest.main()
