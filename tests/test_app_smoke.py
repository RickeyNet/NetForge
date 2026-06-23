"""Smoke test: the whole App (every tab) constructs without error.

This is the safety net for tab refactors - it builds Generate, Models,
Roles, Profiles, Base, and Guide against the real bundled data and
round-trips every profile through the editors.

It runs in a *subprocess*: creating and destroying a Tk root pollutes the
Tcl interpreter, so a second tk.Tk() in the same process fails on some Tk
builds ("invalid command name tcl_findLibrary"). Isolating the App's Tk
lifecycle in its own process keeps it from breaking other GUI tests.
Skips cleanly where Tk has no display.
"""

import os
import subprocess
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Exit code the child uses to say "no display, please skip".
_SKIP_CODE = 99

_SMOKE = r"""
import sys
import tkinter as tk
try:
    root = tk.Tk()
except tk.TclError:
    sys.exit(99)
root.withdraw()
from netforge.app import App
app = App(root)
assert len(app.nb.tabs()) >= 5, "expected the editor tabs plus the guide"
assert hasattr(app.profiles_tab, "bgp_blocks")
assert hasattr(app.gen_tab, "pa_rows")
# Load every bundled profile through the editor and run the collectors -
# exercises the BGP/ACL/SVI sub-editors without writing to disk.
pt = app.profiles_tab
for name in list(app.profiles):
    pt._on_select(name)
    assert isinstance(pt._collect_bgp_instances(), list)
    assert isinstance(pt._collect_acls(), list)
root.destroy()
print("SMOKE_OK")
"""


class TestAppSmoke(unittest.TestCase):
    def test_app_builds_all_tabs(self):
        proc = subprocess.run(
            [sys.executable, "-c", _SMOKE],
            cwd=_REPO_ROOT, capture_output=True, text=True)
        if proc.returncode == _SKIP_CODE:
            self.skipTest("Tk unavailable (no display)")
        self.assertEqual(
            proc.returncode, 0,
            msg=f"smoke build failed\nSTDOUT:\n{proc.stdout}\n"
                f"STDERR:\n{proc.stderr}")
        self.assertIn("SMOKE_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
