"""Tests for the shared input validators."""

import unittest

from netforge.validate import (
    field_errors,
    is_ipv4,
    is_ipv4_mask,
    is_vlan_id,
    validate_switch_config,
)


class TestPrimitives(unittest.TestCase):
    def test_ipv4(self):
        self.assertTrue(is_ipv4("10.0.0.1"))
        self.assertTrue(is_ipv4(" 192.168.1.254 "))
        self.assertFalse(is_ipv4("10.0.0.256"))
        self.assertFalse(is_ipv4("10.0.0"))
        self.assertFalse(is_ipv4("hello"))
        self.assertFalse(is_ipv4(""))

    def test_ipv4_mask(self):
        for good in ("255.255.255.0", "255.255.255.252", "255.0.0.0",
                     "255.255.255.255", "0.0.0.0"):
            self.assertTrue(is_ipv4_mask(good), good)
        for bad in ("255.0.255.0", "255.255.1.0", "255.255.255.1",
                    "1.2.3.4", "not.a.mask"):
            self.assertFalse(is_ipv4_mask(bad), bad)

    def test_vlan_id(self):
        self.assertTrue(is_vlan_id("1"))
        self.assertTrue(is_vlan_id("4094"))
        self.assertTrue(is_vlan_id(100))
        self.assertFalse(is_vlan_id("0"))
        self.assertFalse(is_vlan_id("4095"))
        self.assertFalse(is_vlan_id("ten"))


class TestFieldErrors(unittest.TestCase):
    def test_blank_values_pass(self):
        self.assertEqual(field_errors([("Gateway", "", "ip"),
                                       ("Mask", None, "mask")]), [])

    def test_flags_bad_values(self):
        errs = field_errors([
            ("Management IP", "10.0.0.999", "ip"),
            ("Netmask", "255.255.0.255", "mask"),
            ("DNS", "8.8.8.8, bogus", "ip_csv"),
            ("Gateway", "10.0.0.1", "ip"),   # good - no error
        ])
        self.assertEqual(len(errs), 3)
        self.assertTrue(any("Management IP" in e for e in errs))

    def test_csv_all_valid(self):
        self.assertEqual(
            field_errors([("DNS", "8.8.8.8, 1.1.1.1", "ip_csv")]), [])


class TestValidateSwitchConfig(unittest.TestCase):
    def test_clean_config_has_no_errors(self):
        sw = {"mgmt_ip": "10.0.0.2", "mgmt_mask": "255.255.255.0",
              "default_gateway": "10.0.0.1",
              "svis": [{"vlan": "10", "ip": "10.10.0.1",
                        "mask": "255.255.255.0",
                        "helper_addresses": ["10.99.0.5"]}]}
        profile = {"port_assignments": [
            {"interfaces": "range Gi1/0/1-10", "role": "access"},
            {"interfaces": "Gi1/0/24", "role": "uplink"}]}
        errors, warnings = validate_switch_config({}, profile, {}, {}, sw)
        self.assertEqual(errors, [])

    def test_bad_addresses_and_vlan_flagged(self):
        sw = {"mgmt_ip": "10.0.0.300", "mgmt_mask": "255.255.0.255",
              "svis": [{"vlan": "5000", "ip": "1.1.1.1",
                        "mask": "255.255.255.0"}]}
        errors, _ = validate_switch_config({}, {}, {}, {}, sw)
        self.assertTrue(any("Management IP" in e for e in errors))
        self.assertTrue(any("mask" in e for e in errors))
        self.assertTrue(any("VLAN" in e for e in errors))

    def test_duplicate_interface_flagged(self):
        # Gi1/0/5 appears in the range AND as an explicit assignment.
        profile = {"port_assignments": [
            {"interfaces": "range Gi1/0/1-5", "role": "access"},
            {"interfaces": "Gi1/0/5", "role": "uplink"}]}
        errors, _ = validate_switch_config({}, profile, {}, {}, {})
        self.assertTrue(any("Gi1/0/5" in e and "more than one" in e
                            for e in errors))


class TestRoleVariableWarnings(unittest.TestCase):
    ROLES = {
        "Access": {"commands": "switchport access vlan {{ user_vlan }}\n"
                                "description {{ description }}"},
        "Uplink": {"commands": "ip address {{ ip }} {{ mask }}",
                   "requires_ip": True},
    }

    def test_undefined_variable_warns(self):
        profile = {"role_variables": {},
                   "port_assignments": [{"interfaces": "Gi1/0/1",
                                         "role": "Access"}]}
        _, warnings = validate_switch_config({}, profile, self.ROLES, {}, {})
        self.assertTrue(any("user_vlan" in w for w in warnings))
        # description is a built-in, so it must NOT be flagged.
        self.assertFalse(any("description" in w for w in warnings))

    def test_defined_variable_and_builtins_dont_warn(self):
        profile = {"role_variables": {"user_vlan": "10"},
                   "port_assignments": [
                       {"interfaces": "Gi1/0/1", "role": "Access"},
                       {"interfaces": "Gi1/0/24", "role": "Uplink"}]}
        _, warnings = validate_switch_config({}, profile, self.ROLES, {}, {})
        self.assertEqual(warnings, [])


class TestUnusedRoleVariableWarnings(unittest.TestCase):
    ROLES = {"Access": {"commands": "switchport access vlan "
                                    "{{ access_vlan }}"}}

    def test_unused_variable_warns(self):
        profile = {"role_variables": {"access_vlan": "10",
                                      "acccess_vlan": "10"},  # typo
                   "port_assignments": [{"interfaces": "Gi1/0/1",
                                         "role": "Access"}]}
        _, warnings = validate_switch_config({}, profile, self.ROLES, {}, {})
        self.assertTrue(any("acccess_vlan" in w and "not used" in w
                            for w in warnings))
        # The correctly-spelled one is referenced, so no warning for it.
        self.assertFalse(any("'access_vlan'" in w for w in warnings))

    def test_variable_used_only_in_base_is_not_unused(self):
        profile = {"role_variables": {"ntp_server_1": "1.1.1.1"},
                   "port_assignments": []}
        base = {"ntp": "ntp server {{ ntp_server_1 }}"}
        _, warnings = validate_switch_config({}, profile, {}, base, {})
        self.assertEqual(warnings, [])


class TestUnknownInterfaceWarnings(unittest.TestCase):
    MODEL = {"port_groups": [
        {"prefix": "GigabitEthernet1/0/", "start": 1, "end": 24}]}

    def _warn(self, interfaces, model=None):
        profile = {"port_assignments": [{"interfaces": interfaces,
                                         "role": "x"}]}
        _, warnings = validate_switch_config(model or self.MODEL,
                                             profile, {}, {}, {})
        return warnings

    def test_port_out_of_range_warns(self):
        self.assertTrue(any("Gi1/0/48" in w
                            for w in self._warn("Gi1/0/48")))

    def test_abbreviation_in_range_is_ok(self):
        # Gi1/0/10 == GigabitEthernet1/0/10, which exists -> no warning.
        self.assertEqual(self._warn("Gi1/0/10"), [])

    def test_other_family_not_flagged(self):
        # Port-channel isn't a family the model defines -> not flagged.
        self.assertEqual(self._warn("Port-channel1"), [])

    def test_stack_member_beyond_size_warns(self):
        # Single-unit model: a member-2 port should be flagged.
        self.assertTrue(any("Gi2/0/1" in w
                            for w in self._warn("Gi2/0/1")))

    def test_range_expansion_flags_only_the_bad_ports(self):
        warnings = self._warn("range GigabitEthernet1/0/20-26")
        # 20-24 exist; 25 and 26 do not.
        self.assertTrue(any("1/0/25" in w for w in warnings))
        self.assertTrue(any("1/0/26" in w for w in warnings))
        self.assertFalse(any("1/0/24" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
