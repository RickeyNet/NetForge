"""Tests for netforge.data.base_settings."""

import unittest

from netforge.data.base_settings import _migrate_base_set, load_base_settings
import netforge.data.storage as storage


class TestMigrateBaseSet(unittest.TestCase):
    def test_migrates_legacy_keys(self):
        entry = {
            "global_services": "service timestamps debug",
            "aaa": "aaa new-model",
            "security": "no ip source-route",
            "switching": "spanning-tree mode rapid-pvst",
        }
        _migrate_base_set(entry)
        self.assertIn("service timestamps debug", entry["services_functions"])
        self.assertIn("aaa new-model", entry["aaa_radius"])
        self.assertNotIn("global_services", entry)
        self.assertNotIn("aaa", entry)

    def test_idempotent(self):
        entry = {"services_functions": "already migrated"}
        _migrate_base_set(entry)
        _migrate_base_set(entry)
        self.assertEqual(entry["services_functions"], "already migrated")

    def test_drops_legacy_sections(self):
        entry = {"ntp": "ntp server 1.1.1.1", "ssh": "ip ssh version 2"}
        _migrate_base_set(entry)
        self.assertNotIn("ntp", entry)
        self.assertEqual(entry["ssh"], "ip ssh version 2")


class TestLoadBaseSettings(unittest.TestCase):
    def test_legacy_flat_wrapped_as_base(self):
        orig = storage.load_json
        try:
            storage.load_json = lambda name, default=None: {
                "ssh": "ip ssh version 2",
            }
            root = load_base_settings()
            self.assertEqual(root["default"], "Base")
            self.assertIn("ssh", root["sets"]["Base"])
        finally:
            storage.load_json = orig


if __name__ == "__main__":
    unittest.main()
