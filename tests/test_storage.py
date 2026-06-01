"""Tests for netforge.data.storage."""

import json
import os
import tempfile
import unittest

import netforge.data.storage as storage


class TestStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_data_dir = storage.DATA_DIR
        storage.DATA_DIR = self._tmpdir.name

    def tearDown(self):
        storage.DATA_DIR = self._orig_data_dir
        self._tmpdir.cleanup()

    def test_save_and_load_json(self):
        storage.save_json("test.json", {"a": 1})
        self.assertEqual(storage.load_json("test.json"), {"a": 1})

    def test_load_missing_returns_default(self):
        self.assertEqual(storage.load_json("missing.json", {"x": 2}), {"x": 2})

    def test_load_missing_returns_empty_dict(self):
        self.assertEqual(storage.load_json("missing.json"), {})


class TestMergeBundledData(unittest.TestCase):
    def test_merge_adds_new_keys_without_overwriting(self):
        with tempfile.TemporaryDirectory() as bundled, \
                tempfile.TemporaryDirectory() as live:
            orig_bundle = storage._BUNDLE_DIR
            orig_data = storage.DATA_DIR
            try:
                storage._BUNDLE_DIR = bundled
                storage.DATA_DIR = live
                bundled_models = os.path.join(bundled, "data")
                os.makedirs(bundled_models)
                with open(os.path.join(bundled_models, "models.json"),
                          "w", encoding="utf-8") as f:
                    json.dump({"NewModel": {}, "Shared": {"a": 1}}, f)
                with open(os.path.join(live, "models.json"),
                          "w", encoding="utf-8") as f:
                    json.dump({"Shared": {"a": 99}, "Local": {}}, f)
                storage.merge_bundled_data()
                with open(os.path.join(live, "models.json"),
                          encoding="utf-8") as f:
                    merged = json.load(f)
                self.assertIn("NewModel", merged)
                self.assertIn("Local", merged)
                self.assertEqual(merged["Shared"]["a"], 99)
            finally:
                storage._BUNDLE_DIR = orig_bundle
                storage.DATA_DIR = orig_data


if __name__ == "__main__":
    unittest.main()
