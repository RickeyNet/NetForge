"""Theme presets, palette, and ttk styling."""

import tkinter as tk
from tkinter import ttk

from netforge.data.storage import load_json, save_json

# ---------------------------------------------------------------------------
# Theme presets
# ---------------------------------------------------------------------------
THEMES = {
    "default": {
        "name":         "Default",
        "bg":           "#1a1a1a",
        "bg2":          "#242424",
        "bg_input":     "#2d2d2d",
        "fg":           "#d4d4d4",
        "fg_dim":       "#909090",
        "accent":       "#b0b0b0",
        "accent_hover": "#c8c8c8",
        "border":       "#3c3c3c",
        "green":        "#a6e3a1",
        "red":          "#c75050",
        "red_hover":    "#d06060",
        "sel_bg":       "#3c3c3c",
    },
    "ocean_coral": {
        "name":         "Coral",
        "bg":           "#0b1e24",
        "bg2":          "#112e35",
        "bg_input":     "#163a45",
        "fg":           "#e0d4bc",
        "fg_dim":       "#7a9a8a",
        "accent":       "#f08a65",
        "accent_hover": "#f4a080",
        "border":       "#1a4450",
        "green":        "#8abb6a",
        "red":          "#e05555",
        "red_hover":    "#e87070",
        "sel_bg":       "#1a4450",
    },
    "sandstone": {
        "name":         "Sandstone",
        "bg":           "#4f5544",
        "bg2":          "#3e4337",
        "bg_input":     "#2e3128",
        "fg":           "#d8d2bc",
        "fg_dim":       "#9a9480",
        "accent":       "#c97b3a",
        "accent_hover": "#e0934a",
        "border":       "#2a2d23",
        "green":        "#a3b878",
        "red":          "#a83e3e",
        "red_hover":    "#c25555",
        "sel_bg":       "#5c6450",
    },
    "chris": {
        "name":         "Chris",
        "bg":           "#ff69b4",
        "bg2":          "#ff85c2",
        "bg_input":     "#ff3399",
        "fg":           "#1b00ff",
        "fg_dim":       "#ff6600",
        "accent":       "#00ff00",
        "accent_hover": "#ffff00",
        "border":       "#8b00ff",
        "green":        "#ff0000",
        "red":          "#00ffff",
        "red_hover":    "#39ff14",
        "sel_bg":       "#ffd700",
    },
    "voyager": {
        "name":         "Voyager",
        "bg":           "#0f1a3d",
        "bg2":          "#19234d",
        "bg_input":     "#070d24",
        "fg":           "#e6ebf5",
        "fg_dim":       "#7d89b0",
        "accent":       "#f5a623",
        "accent_hover": "#ffb840",
        "border":       "#1f2a5c",
        "green":        "#7dd3a0",
        "red":          "#e05555",
        "red_hover":    "#e87070",
        "sel_bg":       "#1f2a5c",
    },
    "light": {
        "name":         "Light",
        "bg":           "#f0f0eb",
        "bg2":          "#e2e2dc",
        "bg_input":     "#ffffff",
        "fg":           "#1e1e1e",
        "fg_dim":       "#6a6a6a",
        "accent":       "#0066cc",
        "accent_hover": "#0055aa",
        "border":       "#c0bfb5",
        "green":        "#1a6e1a",
        "red":          "#cc3333",
        "red_hover":    "#aa2222",
        "sel_bg":       "#cce0ff",
    },
}

# Ordered list of (key, display-label) pairs that define a complete theme.
# Used by the custom theme editor to render one color row per entry.
THEME_KEYS = [
    ("bg",           "Background"),
    ("bg2",          "Panel Background"),
    ("bg_input",     "Input Background"),
    ("fg",           "Foreground"),
    ("fg_dim",       "Foreground Dim"),
    ("accent",       "Accent"),
    ("accent_hover", "Accent Hover"),
    ("border",       "Border / Selection"),
    ("green",        "Config Text"),
    ("red",          "Danger / Delete"),
    ("red_hover",    "Danger Hover"),
    ("sel_bg",       "Item Highlight"),
]

# Active colour palette - starts with default, updated by _load_theme()
C = dict(THEMES["default"])


def _load_theme():
    """Load the saved theme preference and apply it to C."""
    saved = load_json("theme.json", {})
    tid = saved.get("theme", "default")
    if tid in THEMES:
        C.update(THEMES[tid])
    else:
        custom = saved.get("custom_themes", {})
        if tid in custom:
            C.update(custom[tid])


def _save_theme(tid):
    """Persist the selected theme id, preserving any custom_themes data."""
    saved = load_json("theme.json", {})
    saved["theme"] = tid
    save_json("theme.json", saved)


def apply_theme(root):
    root.configure(bg=C["bg"])
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".",          background=C["bg"], foreground=C["fg"],
                borderwidth=0, focuscolor=C["accent"])
    s.configure("TFrame",    background=C["bg"])
    s.configure("TLabel",    background=C["bg"], foreground=C["fg"])
    s.configure("Sec.TLabel", background=C["bg"], foreground=C["fg"],
                font=("Segoe UI", 10, "bold"))
    s.configure("Hint.TLabel", background=C["bg"], foreground=C["fg_dim"],
                font=("Segoe UI", 8))
    s.configure("TLabelframe",       background=C["bg"], foreground=C["fg"],
                bordercolor=C["border"])
    s.configure("TLabelframe.Label", background=C["bg"], foreground=C["fg"],
                font=("Segoe UI", 9, "bold"))
    s.configure("TEntry", fieldbackground=C["bg_input"], foreground=C["fg"],
                insertcolor=C["fg"], bordercolor=C["border"],
                lightcolor=C["border"], darkcolor=C["border"])
    s.map("TEntry",
          bordercolor=[("focus", C["accent"])],
          lightcolor=[("focus", C["accent"])],
          darkcolor=[("focus", C["accent"])])
    s.configure("TButton", background=C["accent"], foreground=C["bg"],
                font=("Segoe UI", 9, "bold"), padding=(10, 4),
                bordercolor=C["accent"],
                lightcolor=C["accent"], darkcolor=C["accent"])
    s.map("TButton",
          background=[("active", C["accent_hover"])],
          bordercolor=[("focus", C["fg"])],
          lightcolor=[("focus", C["fg"])],
          darkcolor=[("focus", C["fg"])])
    s.configure("Del.TButton", background=C["red"], foreground="#fff",
                font=("Segoe UI", 9, "bold"), padding=(4, 2),
                bordercolor=C["red"],
                lightcolor=C["red"], darkcolor=C["red"])
    s.map("Del.TButton",
          background=[("active", C["red_hover"])],
          bordercolor=[("focus", C["fg"])],
          lightcolor=[("focus", C["fg"])],
          darkcolor=[("focus", C["fg"])])
    s.configure("TNotebook",     background=C["bg"], borderwidth=0)
    s.configure("TNotebook.Tab", background=C["bg2"], foreground=C["fg"],
                padding=(14, 6), font=("Segoe UI", 9, "bold"))
    s.map("TNotebook.Tab",
          background=[("selected", C["bg"]), ("active", C["border"])])
    s.configure("TCombobox", fieldbackground=C["bg_input"],
                foreground=C["fg"], bordercolor=C["border"],
                lightcolor=C["border"], darkcolor=C["border"],
                arrowcolor=C["fg"])
    s.map("TCombobox",
          fieldbackground=[("readonly", C["bg_input"])],
          foreground=[("readonly", C["fg"])],
          bordercolor=[("focus", C["accent"])],
          lightcolor=[("focus", C["accent"])],
          darkcolor=[("focus", C["accent"])])
    root.option_add("*TCombobox*Listbox.background", C["bg_input"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["border"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["fg"])
    s.configure("TCheckbutton", background=C["bg"], foreground=C["fg"],
                indicatorbackground=C["bg_input"],
                indicatorforeground=C["accent"],
                focuscolor=C["bg"])
    s.map("TCheckbutton",
          background=[("active", C["bg"])],
          foreground=[("active", C["fg"])],
          indicatorbackground=[("active", C["bg_input"]),
                               ("selected", C["bg_input"])],
          indicatorforeground=[("active", C["accent"]),
                               ("selected", C["accent"])])
    s.configure("TRadiobutton", background=C["bg"], foreground=C["fg"],
                indicatorbackground=C["bg_input"],
                indicatorforeground=C["accent"],
                focuscolor=C["bg"])
    s.map("TRadiobutton",
          background=[("active", C["bg"])],
          foreground=[("active", C["fg"])],
          indicatorbackground=[("active", C["bg_input"]),
                               ("selected", C["bg_input"])],
          indicatorforeground=[("active", C["accent"]),
                               ("selected", C["accent"])])
    s.configure("TSeparator",         background=C["border"])
    s.configure("Vertical.TScrollbar", background=C["bg2"],
                troughcolor=C["bg"], arrowcolor=C["fg_dim"])
    s.configure("TPanedwindow", background=C["border"])
    s.configure("StepActive.TLabel",  background=C["bg"], foreground="#ffffff",
                font=("Segoe UI", 10, "bold"))
    s.configure("StepDone.TLabel",    background=C["bg"], foreground=C["green"],
                font=("Segoe UI", 10))
    s.configure("StepPending.TLabel", background=C["bg"], foreground=C["fg_dim"],
                font=("Segoe UI", 10))
    s.configure("StepArrow.TLabel",   background=C["bg"], foreground=C["fg_dim"],
                font=("Segoe UI", 10))

    from netforge.ui.win_theme import _restyle_all_windows

    _restyle_all_windows()
