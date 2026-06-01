"""Unit tests for theme loading and palette."""

import tempfile
import unittest

import netforge.data.storage as storage
from netforge.ui.theme import C, THEMES, _load_theme, _save_theme, apply_theme


class TestTheme(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_data_dir = storage.DATA_DIR
        storage.DATA_DIR = self._tmpdir.name
        C.update(THEMES["default"])

    def tearDown(self):
        storage.DATA_DIR = self._orig_data_dir
        self._tmpdir.cleanup()
        C.update(THEMES["default"])

    def test_default_palette_has_required_keys(self):
        for key, _label in [
            ("bg", ""),
            ("fg", ""),
            ("accent", ""),
            ("border", ""),
        ]:
            self.assertIn(key, C)
            self.assertTrue(C[key])

    def test_all_presets_complete(self):
        required = {k for k, _ in [
            ("bg", ""),
            ("bg2", ""),
            ("bg_input", ""),
            ("fg", ""),
            ("fg_dim", ""),
            ("accent", ""),
            ("accent_hover", ""),
            ("border", ""),
            ("green", ""),
            ("red", ""),
            ("red_hover", ""),
            ("sel_bg", ""),
        ]}
        for tid, theme in THEMES.items():
            missing = required - set(theme)
            self.assertEqual(missing, set(), f"{tid} missing {missing}")

    def test_save_and_load_theme(self):
        import tkinter as tk

        _save_theme("light")
        _load_theme()
        self.assertEqual(C["bg"], THEMES["light"]["bg"])

        root = tk.Tk()
        root.withdraw()
        try:
            apply_theme(root)
            style = root.tk.call("ttk::style", "lookup", "TFrame", "-background")
            self.assertEqual(style, C["bg"])
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
