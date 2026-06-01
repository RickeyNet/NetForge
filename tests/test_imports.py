"""Smoke tests for package imports."""

import unittest


class TestImports(unittest.TestCase):
    def test_netforge_version(self):
        import netforge
        self.assertEqual(netforge.VERSION, "1.4.0")

    def test_data_modules(self):
        from netforge.data import storage, base_settings, iface
        self.assertTrue(callable(storage.load_json))
        self.assertTrue(callable(base_settings.load_base_settings))
        self.assertTrue(callable(iface.expand_range_iface))

    def test_ui_filename_template(self):
        from netforge.ui.filename_template import apply_filename_template
        self.assertTrue(callable(apply_filename_template))

    def test_netforge_py_imports(self):
        import NetForge
        self.assertTrue(hasattr(NetForge, "main"))


if __name__ == "__main__":
    unittest.main()
