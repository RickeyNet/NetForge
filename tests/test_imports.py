"""Smoke tests for package imports."""

import unittest


class TestImports(unittest.TestCase):
    def test_netforge_version(self):
        import netforge
        self.assertRegex(netforge.VERSION, r"^\d+\.\d+\.\d+$")

    def test_data_modules(self):
        from netforge.data import storage, base_settings, iface
        self.assertTrue(callable(storage.load_json))
        self.assertTrue(callable(base_settings.load_base_settings))
        self.assertTrue(callable(iface.expand_range_iface))

    def test_ui_filename_template(self):
        from netforge.ui.filename_template import apply_filename_template
        self.assertTrue(callable(apply_filename_template))

    def test_ui_theme_modules(self):
        from netforge.ui import theme, win_theme, widgets, helpers
        self.assertIn("default", theme.THEMES)
        self.assertTrue(callable(theme.apply_theme))
        self.assertTrue(callable(win_theme._style_window))
        self.assertTrue(callable(widgets.PanedWindow))
        self.assertTrue(callable(helpers._dialog))

    def test_render_modules(self):
        from netforge.render import render_config, render_config_sections
        self.assertTrue(callable(render_config))
        self.assertTrue(callable(render_config_sections))

    def test_dialog_modules(self):
        from netforge.serial_push import _SerialPushDialog
        from netforge.ui.theme_editor import _ThemeEditorDialog
        self.assertTrue(callable(_SerialPushDialog))
        self.assertTrue(callable(_ThemeEditorDialog))

    def test_ftd_modules(self):
        from netforge.ftd.console import ExpectSession, initial_setup_rules
        from netforge.ftd.fdm_api import FdmClient
        from netforge.ftd.dialog import FtdTab
        self.assertTrue(callable(ExpectSession))
        self.assertTrue(callable(initial_setup_rules))
        self.assertTrue(callable(FdmClient))
        self.assertTrue(callable(FtdTab))

    def test_serial_common_module(self):
        from netforge.serial_common import (
            BAUD_RATES,
            open_console_port,
            refresh_com_ports,
        )
        self.assertIn("9600", BAUD_RATES)
        self.assertTrue(callable(open_console_port))
        self.assertTrue(callable(refresh_com_ports))

    def test_tab_modules(self):
        from netforge.tabs import (
            BaseTab,
            FtdTab,
            GenerateTab,
            GuideTab,
            ModelsTab,
            ProfilesTab,
            RolesTab,
        )
        for cls in (BaseTab, FtdTab, GenerateTab, GuideTab, ModelsTab,
                    ProfilesTab, RolesTab):
            self.assertTrue(issubclass(cls, __import__("tkinter").ttk.Frame))

    def test_l3_grid_module(self):
        from netforge.ui.l3_grid import L3EntryGrid
        self.assertTrue(callable(L3EntryGrid))

    def test_app_module(self):
        from netforge.app import App, main
        self.assertTrue(callable(App))
        self.assertTrue(callable(main))

    def test_netforge_py_imports(self):
        import NetForge
        self.assertTrue(hasattr(NetForge, "main"))
        self.assertTrue(hasattr(NetForge, "App"))


if __name__ == "__main__":
    unittest.main()
