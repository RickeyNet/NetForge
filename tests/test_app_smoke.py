"""Smoke test: the whole App (every tab) constructs without error.

This is the safety net for tab refactors - it actually builds Generate,
Models, Roles, Profiles, Base, and Guide against the real bundled data.
Skips cleanly where Tk has no display.
"""

import tkinter as tk
import unittest


class TestAppSmoke(unittest.TestCase):
    def test_app_builds_all_tabs(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:               # headless / no display
            self.skipTest(f"Tk unavailable: {exc}")
        root.withdraw()
        try:
            from netforge.app import App
            app = App(root)
            # Notebook has the editor tabs plus the guide.
            self.assertGreaterEqual(len(app.nb.tabs()), 5)
            # The two mega-tabs in particular built their editors.
            self.assertTrue(hasattr(app.profiles_tab, "bgp_blocks"))
            self.assertTrue(hasattr(app.gen_tab, "pa_rows"))

            # Load every bundled profile through the editor and run the
            # collectors. This exercises the BGP/ACL/SVI sub-editors
            # (add-block, add-slot, advertising fields, collect) without
            # writing to disk - the real coverage behind the smoke test.
            pt = app.profiles_tab
            for name in list(app.profiles):
                pt._on_select(name)
                self.assertIsInstance(pt._collect_bgp_instances(), list)
                self.assertIsInstance(pt._collect_acls(), list)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
