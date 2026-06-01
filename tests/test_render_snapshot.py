"""Golden-config snapshot tests for the config renderer."""

import hashlib
import json
import unittest
from pathlib import Path

from netforge.data.base_settings import load_base_settings, resolve_base
from netforge.render import render_config, render_config_sections

FIXTURES = Path(__file__).resolve().parent / "fixtures"
META = json.loads((FIXTURES / "render_snapshots.json").read_text(encoding="utf-8"))


def _base():
    return resolve_base(load_base_settings(), "Base")


L2_MODEL = {
    "provision": "",
    "stack_members": 1,
    "port_groups": [
        {"prefix": "GigabitEthernet1/0/", "start": 1, "end": 4},
        {"prefix": "GigabitEthernet0/", "start": 0, "end": 0},
    ],
}
L2_PROFILE = {
    "mgmt_vlan": "10",
    "vlan_definitions": "vlan 10\n name mgmt\nexit",
    "port_assignments": [
        {
            "role": "Access Port",
            "interfaces": "GigabitEthernet1/0/1",
            "description": "User1",
        }
    ],
    "role_variables": {"user_vlan": "20"},
    "layer3": False,
}
L2_ROLES = {
    "Access Port": {
        "commands": (
            "description {{ description }}\n"
            "switchport access vlan {{ user_vlan }}\n"
            "no shut"
        ),
    },
}
L2_SW = {
    "hostname": "sw-test01",
    "enable_secret": "enc",
    "domain_name": "example.com",
    "mgmt_ip": "10.0.0.1",
    "mgmt_mask": "255.255.255.0",
    "default_gateway": "10.0.0.254",
    "work_order": "WO123",
    "users": [{"name": "admin", "password": "pw", "privilege": 15}],
}

L3_MODEL = {
    "provision": "c9300-24s",
    "stack_members": 1,
    "port_groups": [{"prefix": "GigabitEthernet1/0/", "start": 1, "end": 2}],
}
L3_PROFILE = {
    "mgmt_vlan": "2",
    "layer3": True,
    "vlan_definitions": "vlan 2\n name mgmt\nexit",
    "port_assignments": [],
    "role_variables": {},
    "l3_sections": {
        "loopback": {
            "enabled": True,
            "entries": [
                {
                    "number": "0",
                    "ip": "1.1.1.1",
                    "mask": "255.255.255.255",
                    "description": "RID",
                }
            ],
        },
        "routed_mgmt": {"enabled": False},
        "mgmt_svi": {
            "enabled": True,
            "entries": [
                {
                    "vlan": "2",
                    "ip": "10.0.0.1",
                    "mask": "255.255.255.248",
                    "description": "MGMT",
                }
            ],
        },
    },
    "svis": [],
    "services": {"ntp": {"commands": "ntp server 10.0.0.10"}},
    "acls": [
        {
            "name": "TEST_ACL",
            "type": "extended",
            "rules": [
                {
                    "action": "permit",
                    "protocol": "ip",
                    "source": "any",
                    "dest": "any",
                    "log": True,
                }
            ],
        }
    ],
}
L3_SW = {
    "hostname": "l3-sw01",
    "enable_secret": "enc",
    "domain_name": "example.com",
    "default_gateway": "10.0.0.254",
    "work_order": "",
    "users": [{"name": "admin", "password": "pw", "privilege": 15}],
    "loopbacks": [
        {
            "number": "0",
            "ip": "1.1.1.1",
            "mask": "255.255.255.255",
            "description": "RID",
        }
    ],
    "mgmt_svis": [
        {
            "vlan": "2",
            "ip": "10.0.0.2",
            "mask": "255.255.255.248",
            "description": "Site MGMT",
        }
    ],
}

CASES = {
    "l2_basic": (L2_MODEL, L2_PROFILE, L2_ROLES, _base(), L2_SW),
    "l3_loopback_mgmt_acl": (L3_MODEL, L3_PROFILE, {}, _base(), L3_SW),
}


class TestRenderSnapshot(unittest.TestCase):
    def test_full_config_matches_golden_file(self):
        for name, args in CASES.items():
            with self.subTest(name=name):
                expected = (FIXTURES / f"render_{name}.txt").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(render_config(*args), expected)

    def test_config_hash_matches_metadata(self):
        for name, args in CASES.items():
            with self.subTest(name=name):
                cfg = render_config(*args)
                digest = hashlib.sha256(cfg.encode()).hexdigest()
                self.assertEqual(digest, META[name]["sha256"])
                self.assertEqual(len(cfg), META[name]["length"])

    def test_section_hashes_match_metadata(self):
        for name, args in CASES.items():
            with self.subTest(name=name):
                sections = render_config_sections(*args)
                for key, expected_hash in META[name]["sections"].items():
                    block = sections.get(key, "")
                    digest = hashlib.sha256(block.encode()).hexdigest() if block else ""
                    self.assertEqual(digest, expected_hash, msg=key)

    def test_l2_spot_checks(self):
        cfg = render_config(*CASES["l2_basic"])
        self.assertIn("hostname sw-test01", cfg)
        self.assertIn("interface vlan10", cfg)
        self.assertIn("switchport access vlan 20", cfg)

    def test_l3_spot_checks(self):
        cfg = render_config(*CASES["l3_loopback_mgmt_acl"])
        self.assertIn("interface Loopback0", cfg)
        self.assertIn("ip access-list extended TEST_ACL", cfg)
        self.assertIn("switch 1 provision c9300-24s", cfg)


if __name__ == "__main__":
    unittest.main()
