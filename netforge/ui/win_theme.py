"""Windows-specific window chrome (DWM dark mode, icon)."""

import ctypes
import os
import sys
import weakref
from ctypes import wintypes


from netforge.data.storage import ICON_PATH
from netforge.ui.theme import C

# Windows DWM attributes (Win10 1809+ for dark-mode; Win11 22H2+ for colors)
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36

_styled_windows = weakref.WeakSet()


def _hex_to_colorref(hex_color):
    """Convert '#rrggbb' to a Win32 COLORREF (0x00bbggrr)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return None
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return None
    return (b << 16) | (g << 8) | r


def _apply_dwm_styling(win):
    """Apply dark-mode + themed border/caption colors to a window's title bar.

    Win10 1809+ honors the dark-mode flag. Win11 22H2+ honors the explicit
    color attributes; older builds silently ignore them.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = wintypes.HWND(int(win.frame(), 16))
    except Exception:
        return
    dwmapi = ctypes.windll.dwmapi
    set_attr = dwmapi.DwmSetWindowAttribute

    dark = wintypes.BOOL(1)
    set_attr(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
             ctypes.byref(dark), ctypes.sizeof(dark))

    for attr, key in (
        (_DWMWA_BORDER_COLOR, "bg2"),
        (_DWMWA_CAPTION_COLOR, "bg2"),
        (_DWMWA_TEXT_COLOR, "fg"),
    ):
        cref = _hex_to_colorref(C.get(key, ""))
        if cref is None:
            continue
        val = wintypes.DWORD(cref)
        set_attr(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))


def _style_window(win):
    """Apply icon + themed DWM title-bar styling. Tracked for theme switches."""
    if os.path.isfile(ICON_PATH):
        try:
            # default=... sets the icon as the application-wide default so
            # every new Toplevel inherits it and Windows uses it on the taskbar.
            win.iconbitmap(default=ICON_PATH)
        except Exception:
            try:
                win.iconbitmap(ICON_PATH)
            except Exception:
                pass
    _styled_windows.add(win)
    # DWM attributes need a real HWND; defer until the window is mapped.
    win.after(10, lambda: _apply_dwm_styling(win))


def _restyle_all_windows():
    """Re-apply DWM colors to every tracked window (called on theme change)."""
    for win in list(_styled_windows):
        try:
            if win.winfo_exists():
                _apply_dwm_styling(win)
        except Exception:
            pass


# Backwards-compatible alias: existing call sites use _apply_icon.
_apply_icon = _style_window
