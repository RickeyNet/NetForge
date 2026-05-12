"""
Cisco Switch Initial Configuration Generator

A Windows GUI application that generates initial configurations for Cisco
switches.  Users define switch models, interface roles, site profiles, and
base settings as reusable presets - then pick a model + profile, fill in a
handful of per-switch values, and click Generate.

All definitions are stored as JSON in the data/ directory and persist between
sessions.  No org-specific data is shipped - everything is user-defined.
"""

import json
import os
import re
import sys
from datetime import date
import tkinter as tk
import zipfile
from tkinter import colorchooser, ttk, filedialog, scrolledtext
from jinja2 import Environment

VERSION = "1.3.0"
_RECENT_MAX = 10


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")

# On first run of a one-file build, seed data/ from bundled defaults
if not os.path.exists(DATA_DIR):
    _bundled_data = os.path.join(_BUNDLE_DIR, "data")
    if os.path.isdir(_bundled_data):
        import shutil
        shutil.copytree(_bundled_data, DATA_DIR)

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
    s.map("TEntry", bordercolor=[("focus", C["accent"])])
    s.configure("TButton", background=C["accent"], foreground=C["bg"],
                font=("Segoe UI", 9, "bold"), padding=(10, 4))
    s.map("TButton", background=[("active", C["accent_hover"])])
    s.configure("Del.TButton", background=C["red"], foreground="#fff",
                font=("Segoe UI", 9, "bold"), padding=(4, 2))
    s.map("Del.TButton", background=[("active", C["red_hover"])])
    s.configure("TNotebook",     background=C["bg"], borderwidth=0)
    s.configure("TNotebook.Tab", background=C["bg2"], foreground=C["fg"],
                padding=(14, 6), font=("Segoe UI", 9, "bold"))
    s.map("TNotebook.Tab",
          background=[("selected", C["bg"]), ("active", C["border"])])
    s.configure("TCombobox", fieldbackground=C["bg_input"],
                foreground=C["fg"], bordercolor=C["border"],
                arrowcolor=C["fg"])
    s.map("TCombobox",
          fieldbackground=[("readonly", C["bg_input"])],
          foreground=[("readonly", C["fg"])])
    root.option_add("*TCombobox*Listbox.background", C["bg_input"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["border"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["fg"])
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


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def load_json(name, default=None):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_base_settings():
    """Load base_settings.json and normalize to the multi-base shape:
        {"sets": {<name>: {...}, ...}, "default": <name>}
    Legacy flat dicts are migrated into a single entry named "Base"."""
    raw = load_json("base_settings.json", {})
    if isinstance(raw, dict) and isinstance(raw.get("sets"), dict):
        sets = {k: v for k, v in raw["sets"].items() if isinstance(v, dict)}
        if not sets:
            sets = {"Base": {}}
        default = raw.get("default") if raw.get("default") in sets \
            else next(iter(sets))
        return {"sets": sets, "default": default}
    # Legacy flat shape (or empty) - wrap as a single "Base" entry.
    flat = raw if isinstance(raw, dict) else {}
    return {"sets": {"Base": flat}, "default": "Base"}


def resolve_base(base_root, name=None):
    """Return the base-settings dict matching *name*, falling back to the
    default entry when the name is missing or unknown."""
    sets = (base_root or {}).get("sets") or {}
    if name and name in sets:
        return sets[name]
    default = (base_root or {}).get("default")
    if default and default in sets:
        return sets[default]
    if sets:
        return next(iter(sets.values()))
    return {}


# Apply saved theme preference now that load_json is available
_load_theme()


def expand_port_groups_for_stack(port_groups, stack_members):
    """Replicate port groups for each member of a switch stack.

    For a prefix like ``GigabitEthernet1/0/`` the leading switch number
    (the ``1`` before the first ``/``) is replaced with each member number
    (1 … *stack_members*).  If the prefix doesn't contain a ``/`` or the
    stack is size 1 the original groups are returned unchanged.

    If the port groups already contain entries for multiple stack members
    (member numbers > 1) they are returned as-is to avoid duplication.
    """
    if stack_members <= 1:
        return list(port_groups)

    # Check if port_groups already include entries for stack members > 1.
    # If so, they were defined explicitly and should not be expanded again.
    for pg in port_groups:
        m = re.match(r'^([A-Za-z-]*)(\d+)(/.*)$', pg["prefix"])
        if m and int(m.group(2)) > 1:
            return list(port_groups)

    expanded = []
    for pg in port_groups:
        prefix = pg["prefix"]
        # Match the switch number before the first slash
        m = re.match(r'^([A-Za-z-]*)(\d+)(/.*)$', prefix)
        if m:
            name_part, _orig_num, tail = m.group(1), m.group(2), m.group(3)
            for member in range(1, stack_members + 1):
                expanded.append({
                    "prefix": f"{name_part}{member}{tail}",
                    "start": pg["start"],
                    "end": pg["end"],
                })
        else:
            # Can't parse switch number - just include as-is
            expanded.append(pg)
    return expanded


def expand_range_iface(iface_str):
    """Expand 'range PrefixN-M' into individual port strings.

    Returns a list of individual interface strings.  If the input is not
    a range specification, the original string is returned in a one-element
    list so callers can always iterate the result.
    """
    s = iface_str.strip()
    if not s.lower().startswith("range "):
        return [s]
    rest = s[6:]                       # strip leading "range "
    m = re.match(r'^(.+?)(\d+)-(\d+)$', rest)
    if not m:
        return [s]
    prefix, start_s, end_s = m.group(1), m.group(2), m.group(3)
    return [f"{prefix}{i}" for i in range(int(start_s), int(end_s) + 1)]


# ---------------------------------------------------------------------------
# Scrollable frame widget
# ---------------------------------------------------------------------------
class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.inner.bind("<Enter>", self._bind_wheel)
        self.inner.bind("<Leave>", self._unbind_wheel)

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._win, width=event.width)

    def _bind_wheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ---------------------------------------------------------------------------
# Right-click context menu
# ---------------------------------------------------------------------------
def _attach_context_menu(widget):
    """Attach a right-click context menu with Cut/Copy/Paste/Select All."""
    def _show(event):
        menu = tk.Menu(widget, tearoff=0,
                       bg=C["bg2"], fg=C["fg"],
                       activebackground=C["border"],
                       activeforeground=C["fg"],
                       relief="flat", bd=1)
        is_text = isinstance(widget, tk.Text)
        is_entry = isinstance(widget, (ttk.Entry, ttk.Combobox))
        readonly = False
        if is_entry:
            readonly = str(widget.cget("state")) in ("readonly", "disabled")
        elif is_text:
            readonly = str(widget.cget("state")) == "disabled"

        has_sel = False
        try:
            if is_text:
                has_sel = bool(widget.tag_ranges("sel"))
            elif is_entry:
                widget.selection_get()
                has_sel = True
        except (tk.TclError, Exception):
            pass

        has_clip = False
        try:
            widget.clipboard_get()
            has_clip = True
        except (tk.TclError, Exception):
            pass

        if not readonly:
            menu.add_command(label="Cut", accelerator="Ctrl+X",
                            state="normal" if has_sel else "disabled",
                            command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", accelerator="Ctrl+C",
                         state="normal" if has_sel else "disabled",
                         command=lambda: widget.event_generate("<<Copy>>"))
        if not readonly:
            menu.add_command(label="Paste", accelerator="Ctrl+V",
                            state="normal" if has_clip else "disabled",
                            command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        if is_text:
            menu.add_command(label="Select All", accelerator="Ctrl+A",
                            command=lambda: (widget.tag_add("sel", "1.0", "end"),
                                             widget.mark_set("insert", "end")))
        elif is_entry:
            menu.add_command(label="Select All", accelerator="Ctrl+A",
                            command=lambda: (widget.select_range(0, "end"),
                                             widget.icursor("end")))
        menu.tk_popup(event.x_root, event.y_root)
    widget.bind("<Button-3>", _show)


# ---------------------------------------------------------------------------
# Reusable form helpers
# ---------------------------------------------------------------------------
def _section(parent, title):
    ttk.Label(parent, text=title, style="Sec.TLabel").pack(
        anchor="w", padx=5, pady=(14, 2))
    ttk.Separator(parent).pack(fill="x", padx=5)


def _field(parent, label, default="", width=35):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    ttk.Label(f, text=label, width=22, anchor="w").pack(side="left")
    e = ttk.Entry(f, width=width)
    e.pack(side="left", fill="x", expand=True)
    if default:
        e.insert(0, default)
    _attach_context_menu(e)
    return e


def _textarea(parent, label, default="", h=5):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    if label:
        ttk.Label(f, text=label, width=22, anchor="nw").pack(side="left")
    t = tk.Text(f, height=h, font=("Consolas", 9),
                bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
                selectbackground=C["sel_bg"], relief="flat", bd=2, wrap="word")
    t.pack(side="left", fill="x", expand=True)
    if default:
        t.insert("1.0", default)
    _attach_context_menu(t)
    return t


def _combo(parent, label, values, width=33):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    ttk.Label(f, text=label, width=22, anchor="w").pack(side="left")
    cb = ttk.Combobox(f, values=values, width=width, state="readonly")
    cb.pack(side="left", fill="x", expand=True)
    return cb


def _copy_name(name, existing):
    """Return a unique copy name not already in *existing*."""
    candidate = f"{name} (copy)"
    n = 1
    while candidate in existing:
        n += 1
        candidate = f"{name} (copy {n})"
    return candidate


def _apply_filename_template(template, *, hostname="", model="", profile="",
                             work_order=""):
    """Expand {{ var }} placeholders in a filename template.

    Supported variables: hostname, model, profile, date (YYYY-MM-DD),
    work_order.
    Returns a sanitized string safe for use as a file name.
    """
    today = date.today().strftime("%Y-%m-%d")
    subs = {"hostname": hostname, "model": model,
            "profile": profile, "date": today,
            "work_order": work_order}
    result = template
    for key, val in subs.items():
        result = result.replace("{{ " + key + " }}", val)
        result = result.replace("{{" + key + "}}", val)
    # remove characters invalid in file names on Windows and Unix
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", result).strip()
    return result or "config"


def _dialog(title, msg, kind="info"):
    """Themed modal info / warning / error dialog."""
    accent = C["red"] if kind == "error" else C["accent"]
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.configure(bg=C["bg"])
    dlg.resizable(False, False)
    dlg.grab_set()
    tk.Frame(dlg, bg=accent, height=3).pack(fill="x")
    inner = ttk.Frame(dlg, padding=(22, 14, 22, 18))
    inner.pack()
    ttk.Label(inner, text=title, style="Sec.TLabel").pack(anchor="w")
    ttk.Label(inner, text=msg, wraplength=320,
              justify="left").pack(anchor="w", pady=(6, 18))
    ttk.Button(inner, text="OK", command=dlg.destroy).pack(anchor="e")
    dlg.update_idletasks()
    try:
        root = dlg.nametowidget(".")
        rx = root.winfo_x() + (root.winfo_width()  - dlg.winfo_width())  // 2
        ry = root.winfo_y() + (root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
    except Exception:
        pass
    dlg.wait_window()


def _ask(title, msg):
    """Themed yes/no confirmation dialog. Returns True if user clicks Yes."""
    result = [False]
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.configure(bg=C["bg"])
    dlg.resizable(False, False)
    dlg.grab_set()
    tk.Frame(dlg, bg=C["red"], height=3).pack(fill="x")
    inner = ttk.Frame(dlg, padding=(22, 14, 22, 18))
    inner.pack()
    ttk.Label(inner, text=title, style="Sec.TLabel").pack(anchor="w")
    ttk.Label(inner, text=msg, wraplength=320,
              justify="left").pack(anchor="w", pady=(6, 18))
    bf = ttk.Frame(inner)
    bf.pack(anchor="e")
    def _yes():
        result[0] = True
        dlg.destroy()
    ttk.Button(bf, text="Yes", style="Del.TButton",
               command=_yes).pack(side="left", padx=(0, 6))
    ttk.Button(bf, text="Cancel", command=dlg.destroy).pack(side="left")
    dlg.update_idletasks()
    try:
        root = dlg.nametowidget(".")
        rx = root.winfo_x() + (root.winfo_width()  - dlg.winfo_width())  // 2
        ry = root.winfo_y() + (root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
    except Exception:
        pass
    dlg.wait_window()
    return result[0]


def _dark_listbox(parent, **kw):
    return tk.Listbox(parent, font=("Consolas", 10),
                      bg=C["bg_input"], fg=C["fg"],
                      selectbackground=C["border"],
                      selectforeground=C["fg"],
                      selectmode="extended",
                      relief="flat", bd=2, **kw)


# ===================================================================
#  CUSTOM THEME EDITOR
# ===================================================================
class _ThemeEditorDialog:
    """Modal dialog for creating and editing custom themes."""

    def __init__(self, app, on_close=None):
        self.app      = app
        self.on_close = on_close
        self._custom      = self._load_custom()   # tid → theme dict
        self._selected_id = None
        self._color_vars  = {}   # key → StringVar
        self._swatches    = {}   # key → tk.Label (colored square)

        dlg = tk.Toplevel()
        self.dlg = dlg
        dlg.title("Custom Theme Editor")
        dlg.configure(bg=C["bg"])
        dlg.resizable(True, True)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", self._close)

        # ── outer layout ─────────────────────────────────────────────
        outer = ttk.Frame(dlg, padding=10)
        outer.pack(fill="both", expand=True)

        # left: list + CRUD buttons
        left = ttk.Frame(outer)
        left.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(left, text="Custom Themes",
                  style="Sec.TLabel").pack(anchor="w", pady=(0, 4))
        self.lb = tk.Listbox(
            left, font=("Consolas", 10),
            bg=C["bg_input"], fg=C["fg"],
            selectbackground=C["border"], selectforeground=C["fg"],
            selectmode="browse", relief="flat", bd=2, width=22, height=16)
        self.lb.pack(fill="both", expand=True)
        self.lb.bind("<<ListboxSelect>>", self._on_select)

        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="New",
                   command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",
                   command=self._dup).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete", style="Del.TButton",
                   command=self._delete).pack(side="left", padx=2)

        # right: editor form
        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="Theme Name").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        self.name_e = ttk.Entry(right, width=26)
        self.name_e.grid(row=0, column=1, columnspan=2,
                         sticky="ew", pady=(0, 6))

        for row_i, (key, label) in enumerate(THEME_KEYS, start=1):
            var = tk.StringVar()
            self._color_vars[key] = var

            ttk.Label(right, text=label).grid(
                row=row_i, column=0, sticky="w", padx=(0, 8), pady=2)

            swatch = tk.Label(right, width=3, relief="groove",
                              cursor="hand2", bg=C["bg_input"])
            swatch.grid(row=row_i, column=1, padx=(0, 4), pady=2, sticky="ns")
            self._swatches[key] = swatch

            ent = ttk.Entry(right, textvariable=var, width=10)
            ent.grid(row=row_i, column=2, sticky="w", pady=2)

            var.trace_add("write", lambda *_, k=key: self._sync_swatch(k))
            swatch.bind("<Button-1>", lambda e, k=key: self._pick_color(k))

        right.columnconfigure(0, weight=1)

        # ── footer buttons ────────────────────────────────────────────
        footer = ttk.Frame(dlg, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="Preview",
                   command=self._preview).pack(side="left", padx=2)
        ttk.Button(footer, text="Save Theme",
                   command=self._save_theme).pack(side="left", padx=2)
        ttk.Button(footer, text="Close",
                   command=self._close).pack(side="right")

        self._refresh_list()
        # pre-select the active custom theme if there is one, else blank slate
        active_tid = load_json("theme.json", {}).get("theme", "default")
        if active_tid in self._custom:
            self._on_select_by_tid(active_tid)
        elif self._custom:
            self._on_select_by_tid(next(iter(self._custom)))
        else:
            self._new()   # seed editor with current active colours

        dlg.update_idletasks()
        try:
            rx = (app.root.winfo_x()
                  + (app.root.winfo_width()  - dlg.winfo_width())  // 2)
            ry = (app.root.winfo_y()
                  + (app.root.winfo_height() - dlg.winfo_height()) // 2)
            dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
        except Exception:
            pass

        dlg.wait_window()

    # ── persistence ───────────────────────────────────────────────────

    def _load_custom(self):
        saved = load_json("theme.json", {})
        return dict(saved.get("custom_themes", {}))

    def _persist(self):
        saved = load_json("theme.json", {})
        saved["custom_themes"] = self._custom
        save_json("theme.json", saved)

    # ── list management ───────────────────────────────────────────────

    def _refresh_list(self):
        self.lb.delete(0, "end")
        for tid, t in self._custom.items():
            self.lb.insert("end", t.get("name", tid))
        if self._selected_id and self._selected_id in self._custom:
            tids = list(self._custom.keys())
            idx  = tids.index(self._selected_id)
            self.lb.selection_set(idx)
            self.lb.see(idx)

    def _on_select(self, _=None):
        sel = self.lb.curselection()
        if not sel:
            return
        tid = list(self._custom.keys())[sel[0]]
        self._on_select_by_tid(tid)

    def _on_select_by_tid(self, tid):
        if tid not in self._custom:
            return
        self._selected_id = tid
        tids = list(self._custom.keys())
        idx  = tids.index(tid)
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(idx)
        self.lb.see(idx)
        t = self._custom[tid]
        self.name_e.delete(0, "end")
        self.name_e.insert(0, t.get("name", tid))
        for key, var in self._color_vars.items():
            var.set(t.get(key, ""))

    # ── color helpers ─────────────────────────────────────────────────

    def _sync_swatch(self, key):
        val = self._color_vars[key].get().strip()
        try:
            self._swatches[key].configure(bg=val)
        except tk.TclError:
            pass

    def _pick_color(self, key):
        current = self._color_vars[key].get().strip() or C["bg"]
        try:
            result = colorchooser.askcolor(
                color=current, title=f"Pick color - {key}",
                parent=self.dlg)
        except Exception:
            return
        if result and result[1]:
            self._color_vars[key].set(result[1])

    # ── unique ID helper ──────────────────────────────────────────────

    def _unique_tid(self, base):
        tid = base
        n   = 2
        while tid in self._custom or tid in THEMES:
            tid = f"{base} {n}"
            n  += 1
        return tid

    # ── CRUD ──────────────────────────────────────────────────────────

    def _new(self):
        self.lb.selection_clear(0, "end")
        self._selected_id = None
        self.name_e.delete(0, "end")
        self.name_e.insert(0, "My Theme")
        for key in self._color_vars:
            self._color_vars[key].set(C.get(key, ""))

    def _dup(self):
        sel = self.lb.curselection()
        if not sel:
            _dialog("No Selection", "Select a theme to duplicate.", "warning")
            return
        tid      = list(self._custom.keys())[sel[0]]
        data     = dict(self._custom[tid])
        existing = [t.get("name", k) for k, t in self._custom.items()]
        new_name = _copy_name(data.get("name", tid), existing)
        new_tid  = self._unique_tid(new_name)
        data["name"]          = new_name
        self._custom[new_tid] = data
        self._selected_id     = new_tid
        self._refresh_list()

    def _delete(self):
        sel = self.lb.curselection()
        if not sel:
            return
        tid  = list(self._custom.keys())[sel[0]]
        name = self._custom[tid].get("name", tid)
        if _ask("Delete Theme", f"Delete custom theme '{name}'?"):
            del self._custom[tid]
            self._persist()
            self._selected_id = None
            self.name_e.delete(0, "end")
            for var in self._color_vars.values():
                var.set("")
            self._refresh_list()
            # if this was the active theme, revert to default
            saved = load_json("theme.json", {})
            if saved.get("theme") == tid:
                self.app._switch_theme("default")

    def _save_theme(self):
        name = self.name_e.get().strip()
        if not name:
            _dialog("Missing", "Enter a theme name.", "warning")
            return
        colors = {}
        for key, var in self._color_vars.items():
            val = var.get().strip()
            if not val:
                _dialog("Missing Color",
                        f"The '{key}' color is empty.", "warning")
                return
            colors[key] = val
        colors["name"] = name
        tid = self._selected_id
        if not tid or tid not in self._custom:
            tid = self._unique_tid(name)
        self._custom[tid] = colors
        self._selected_id = tid
        self._persist()
        self._refresh_list()
        _dialog("Saved", f"Theme '{name}' saved.")

    def _preview(self):
        """Apply the editor's current colors as a live preview."""
        colors = {k: v.get().strip() for k, v in self._color_vars.items()}
        colors["name"] = self.name_e.get().strip() or "Preview"
        for key, val in colors.items():
            if key == "name":
                continue
            if not val:
                _dialog("Missing Color",
                        f"The '{key}' color is empty.", "warning")
                return
            try:
                self.dlg.winfo_rgb(val)
            except tk.TclError:
                _dialog("Invalid Color",
                        f"'{val}' is not a valid color for '{key}'.",
                        "warning")
                return
        C.update(colors)
        apply_theme(self.app.root)
        self.app._refresh_menubar_colors()
        self.app._rebuild_tabs()

    def _close(self):
        self.dlg.destroy()
        if self.on_close:
            self.on_close()


class _CheckList(tk.Frame):
    """Scrollable list where every row has a checkbox and a clickable label."""

    def __init__(self, parent, on_click=None, **kw):
        super().__init__(parent, bg=C["bg_input"], **kw)
        vsb = ttk.Scrollbar(self, orient="vertical")
        vsb.pack(side="right", fill="y")
        self._canvas = tk.Canvas(self, bg=C["bg_input"], bd=0,
                                  highlightthickness=0,
                                  yscrollcommand=vsb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C["bg_input"])
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda _: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win_id, width=e.width))
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._on_click = on_click
        self._vars     = {}   # name → BooleanVar
        self._labels   = {}   # name → tk.Label
        self._frames   = {}   # name → tk.Frame
        self._selected = None

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def populate(self, names):
        for w in self._inner.winfo_children():
            w.destroy()
        self._vars.clear()
        self._labels.clear()
        self._frames.clear()
        self._selected = None
        for name in names:
            self._add_row(name)

    def _add_row(self, name):
        var = tk.BooleanVar()
        row = tk.Frame(self._inner, bg=C["bg_input"])
        row.pack(fill="x", padx=2, pady=1)
        cb = tk.Checkbutton(row, variable=var,
                             bg=C["bg_input"], fg=C["fg"],
                             activebackground=C["bg_input"],
                             selectcolor=C["bg2"],
                             relief="flat", bd=0, cursor="hand2")
        cb.pack(side="left")
        lbl = tk.Label(row, text=name, anchor="w",
                       bg=C["bg_input"], fg=C["fg"],
                       font=("Consolas", 10), cursor="hand2")
        lbl.pack(side="left", fill="x", expand=True, padx=(2, 4))
        for w in (row, lbl):
            w.bind("<Button-1>", lambda e, n=name: self._click(n))
        for w in (row, lbl, cb):
            w.bind("<MouseWheel>", self._on_wheel)
        self._vars[name]   = var
        self._labels[name] = lbl
        self._frames[name] = row

    def _click(self, name):
        if self._selected and self._selected in self._labels:
            self._labels[self._selected].configure(bg=C["bg_input"])
            self._frames[self._selected].configure(bg=C["bg_input"])
        self._selected = name
        self._labels[name].configure(bg=C["sel_bg"])
        self._frames[name].configure(bg=C["sel_bg"])
        if self._on_click:
            self._on_click(name)

    def get_checked(self):
        return [n for n, v in self._vars.items() if v.get()]

    def get_selected(self):
        return self._selected

    def clear_selection(self):
        if self._selected and self._selected in self._labels:
            self._labels[self._selected].configure(bg=C["bg_input"])
            self._frames[self._selected].configure(bg=C["bg_input"])
        self._selected = None

    def select(self, name):
        if name not in self._frames:
            return
        self._click(name)
        self._frames[name].update_idletasks()
        y      = self._frames[name].winfo_y()
        total  = self._inner.winfo_height()
        ch     = self._canvas.winfo_height()
        if total > ch:
            self._canvas.yview_moveto(y / total)

    def select_all(self):
        """Check all checkboxes. If all are already checked, uncheck all."""
        all_checked = all(v.get() for v in self._vars.values()) if self._vars else False
        for v in self._vars.values():
            v.set(not all_checked)


# ===================================================================
#  CONFIG RENDERER
# ===================================================================
def _render_acl(acl):
    """Render one named ACL (extended or standard) from a structured dict."""
    name = (acl.get("name") or "").strip()
    if not name:
        return ""
    acl_type = (acl.get("type") or "extended").strip() or "extended"
    lines = [f"ip access-list {acl_type} {name}"]
    for r in acl.get("rules", []) or []:
        action = (r.get("action") or "").strip()
        if action == "remark":
            text = (r.get("text") or "").strip()
            if text:
                lines.append(f" remark {text}")
            continue
        if action not in ("permit", "deny"):
            continue
        proto = (r.get("protocol") or "ip").strip() or "ip"
        src = (r.get("source") or "").strip()
        src_wc = (r.get("source_wildcard") or "").strip()
        dst = (r.get("dest") or "").strip()
        dst_wc = (r.get("dest_wildcard") or "").strip()
        parts = [f" {action}", proto]
        if src.lower() == "any" or not src:
            parts.append("any" if src.lower() == "any" else "")
        else:
            parts.append(src)
            if src_wc:
                parts.append(src_wc)
        if dst.lower() == "any" or not dst:
            parts.append("any" if dst.lower() == "any" else "")
        else:
            parts.append(dst)
            if dst_wc:
                parts.append(dst_wc)
        if r.get("log"):
            parts.append("log")
        lines.append(" ".join(p for p in parts if p))
    lines.append("exit")
    return "\n".join(lines)


def _normalize_l3_sections(profile):
    """Return the profile's l3_sections dict, building it from a legacy
    `mgmt_style` value when missing. Layer 3 profiles emit Loopback0,
    Routed Mgmt Interface, and Mgmt SVI sections independently based on
    their `enabled` flags. Returned dict is a fresh copy - callers can
    use it for reads but should write through to profile["l3_sections"]
    explicitly if persisting back."""
    sections = profile.get("l3_sections")
    if isinstance(sections, dict) and sections:
        # Fill in missing keys so callers can read without guarding.
        out = {
            "loopback":    {"enabled": False, "ip": "", "mask": "255.255.255.255",
                            "description": "Switch MGMT / Router-ID"},
            "routed_mgmt": {"enabled": False, "interface": "", "ip": "",
                            "mask": "", "description": "Routed Mgmt Uplink"},
            "mgmt_svi":    {"enabled": False, "vlan": "", "ip": "", "mask": "",
                            "description": "Switch MGMT"},
        }
        for k, defaults in out.items():
            block = sections.get(k) or {}
            merged = dict(defaults)
            merged.update({kk: vv for kk, vv in block.items() if vv is not None})
            out[k] = merged
        return out
    # Migrate from legacy mgmt_style.
    style = (profile.get("mgmt_style") or "svi").strip().lower()
    mgmt_vlan = str(profile.get("mgmt_vlan") or "").strip()
    return {
        "loopback": {
            "enabled":     style == "loopback",
            "ip":          "",
            "mask":        "255.255.255.255",
            "description": "Switch MGMT / Router-ID",
        },
        "routed_mgmt": {
            "enabled":     style == "routed_uplink",
            "interface":   "",
            "ip":          "",
            "mask":        "",
            "description": "Routed Mgmt Uplink",
        },
        "mgmt_svi": {
            "enabled":     style == "svi",
            "vlan":        mgmt_vlan,
            "ip":          "",
            "mask":        "",
            "description": "Switch MGMT",
        },
    }


def _render_bgp(profile, sw):
    """Render one `router bgp <asn>` block per BGP instance defined in
    the profile, each followed by its ISP default-route and Null0
    advertisement for the user network.

    Each instance's peers come from the profile's "slots" list (remote
    ASN + description), with the per-switch Peer IP and Password
    supplied via sw['bgp_instances'][i]['peer_fills']. Fills are matched
    to slots by position. Slots with no IP filled in are skipped.
    """
    bgp_p = profile.get("bgp") or {}
    instances = bgp_p.get("instances") or []
    if not instances:
        return ""

    sw_by_asn = {}
    for s in sw.get("bgp_instances", []) or []:
        key = str(s.get("local_asn") or "").strip()
        if key:
            sw_by_asn[key] = s

    blocks = []
    for inst in instances:
        local_asn = str(inst.get("local_asn") or "").strip()
        if not local_asn:
            continue
        default_peer_asn = str(inst.get("peer_asn") or "").strip()

        slots = inst.get("slots")
        if slots is None:
            slots = [{"peer_asn": p.get("peer_asn"),
                      "description": p.get("description")}
                     for p in (inst.get("peers") or [])]

        sw_inst = sw_by_asn.get(local_asn, {})
        fills = sw_inst.get("peer_fills") or []
        user_network  = (sw_inst.get("user_network") or "").strip()
        user_mask     = (sw_inst.get("user_mask")    or "").strip()

        lines = [f"no router bgp {local_asn}",
                 f"router bgp {local_asn}",
                 " bgp log-neighbor-changes"]
        if user_network and user_mask:
            lines.append(f" network {user_network} mask {user_mask}")
        for i, slot in enumerate(slots):
            slot_asn = str(slot.get("peer_asn") or "").strip() \
                or default_peer_asn
            slot_desc = (slot.get("description") or "").strip()
            fill = fills[i] if i < len(fills) else {}
            ip  = (fill.get("peer_ip")  or "").strip()
            pwd = (fill.get("password") or "").strip()
            if not ip:
                continue  # slot left blank for this switch
            if slot_asn:
                lines.append(f" neighbor {ip} remote-as {slot_asn}")
            if slot_desc:
                lines.append(f" neighbor {ip} description {slot_desc}")
            if pwd:
                lines.append(f" neighbor {ip} password {pwd}")
        lines.append(" exit")
        if user_network and user_mask:
            lines.append(f"ip route {user_network} {user_mask} Null0")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def render_config_sections(model, profile, roles, base, sw):
    """Return an ordered dict of named config sections.

    Keys (in order): "Global / Base", "VLANs", "L3 Interfaces",
                     "Interfaces", "Management", "Post-Interface",
                     "Routing", "Line Config", "Banner / End"
    Each value is a ready-to-paste block (empty string if nothing to show).
    Used by render_config() and by the quick-copy toolbar.

    When ``profile["layer3"]`` is true the renderer adds two new sections
    (L3 Interfaces, Routing). The three L3 interface sections (Loopback0,
    Routed Mgmt Interface, Management VLAN) are each independently emitted
    based on ``profile["l3_sections"][<name>].enabled``; legacy profiles
    with only ``mgmt_style`` are migrated by ``_normalize_l3_sections``.
    """
    env = Environment()
    role_vars = profile.get("role_variables", {})
    stack = model.get("stack_members", 1)
    layer3 = bool(profile.get("layer3", False))

    def _r(text):
        try:
            return env.from_string(text).render(**role_vars)
        except Exception:
            return text

    # Per-port IPs entered in Generate Config Step 3 for ports assigned
    # to a role with requires_ip=True. Keyed by interface name.
    routed_iface_ips = sw.get("routed_iface_ips", {}) or {}

    # Build a set of L3-role interface names so the disabled-port pass
    # skips them (they'll be rendered with their role + per-switch IP).
    routed_iface_names = set()
    if layer3:
        for pa in profile.get("port_assignments", []) or []:
            role_name = pa.get("role")
            if not role_name or role_name == "unassigned":
                continue
            role = roles.get(role_name, {}) or {}
            if role.get("requires_ip"):
                iface = (pa.get("interfaces") or "").strip()
                if iface:
                    routed_iface_names.add(iface)

    def build(parts):
        return "\n\n".join(p.strip() for p in parts if p.strip())

    # ── 1  Global / Base ────────────────────────────────────────────────
    gb = []
    wo_line = f"! Work Order: {sw['work_order']}" if sw.get("work_order") else ""
    header = f"!\n! {sw['hostname']} - Generated Configuration"
    if wo_line:
        header += f"\n{wo_line}"
    header += "\n!"
    gb.append(header)
    gb.append("configure terminal")
    gb.append(base.get("global_services", ""))
    gb.append(f"hostname {sw['hostname']}")
    gb.append(base.get("mgmt_vrf", ""))
    gb.append(base.get("logging", ""))
    gb.append(f"enable secret {sw['enable_secret']}")
    username = (sw.get("local_username")
                or base.get("local_username", "admin")
                or "admin")
    gb.append(f"username {username} privilege 0 secret "
              f"{sw['admin_password']}")
    gb.append(base.get("aaa", ""))
    gb.append(base.get("security", ""))
    provision = model.get("provision", "").strip()
    if provision:
        for member in range(1, stack + 1):
            gb.append(f"switch {member} provision {provision}")
    gb.append(f"ip domain name {sw['domain_name']}")
    gb.append(base.get("ssh", ""))
    gb.append(base.get("switching", ""))

    # Per-profile services: DNS name-servers, NTP, clock settings.
    services = profile.get("services", {}) or {}
    dns_servers = services.get("dns_servers") or []
    if isinstance(dns_servers, str):
        dns_servers = [s.strip() for s in dns_servers.split(",") if s.strip()]
    if dns_servers:
        gb.append("ip name-server " + " ".join(dns_servers))

    tz = (services.get("clock_timezone") or "").strip()
    if tz:
        gb.append(f"clock timezone {tz}")
    summer = (services.get("clock_summer_time") or "").strip()
    if summer:
        gb.append(f"clock summer-time {summer}")

    ntp = services.get("ntp") or {}
    ntp_servers = ntp.get("servers") or []
    if isinstance(ntp_servers, str):
        ntp_servers = [s.strip() for s in ntp_servers.split(",") if s.strip()]
    if ntp_servers:
        ntp_lines = []
        source = (ntp.get("source_interface") or "").strip()
        if source:
            ntp_lines.append(f"ntp source {source}")
        key_id = (ntp.get("auth_key_id") or "").strip()
        key = (ntp.get("auth_key") or "").strip()
        if key_id and key:
            ntp_lines.append("ntp authenticate")
            ntp_lines.append(f"ntp authentication-key {key_id} md5 {key}")
            ntp_lines.append(f"ntp trusted-key {key_id}")
        for s in ntp_servers:
            if key_id and key:
                ntp_lines.append(f"ntp server {s} key {key_id}")
            else:
                ntp_lines.append(f"ntp server {s}")
        gb.append("\n".join(ntp_lines))

    # ── 2  VLANs ────────────────────────────────────────────────────────
    vl = []
    vl.append(profile.get("vlan_definitions", ""))
    for cs in base.get("custom_sections", []):
        if cs.get("position") == "pre-interface":
            cmds = cs.get("commands", "").strip()
            if cmds:
                vl.append(_r(cmds))

    # ── 2b  L3 Interfaces ───────────────────────────────────────────────
    # The three mgmt-capable sections (Loopback0, Routed Mgmt Interface,
    # Mgmt SVI) are each emitted independently based on the profile's
    # l3_sections.<name>.enabled flag. Non-mgmt SVIs (gateways for user
    # VLANs, etc.) come from profile["svis"]. Routed uplinks driven by
    # port_assignments with requires_ip=True live in the Interfaces
    # section, not here.
    l3 = []
    l3_sections = _normalize_l3_sections(profile) if layer3 else {}
    if layer3:
        l3.append("ip routing")

        lb_sec = l3_sections.get("loopback", {})
        if lb_sec.get("enabled"):
            lb_ip = (sw.get("loopback0_ip") or lb_sec.get("ip") or "").strip()
            lb_mask = (sw.get("loopback0_mask")
                       or lb_sec.get("mask")
                       or "255.255.255.255").strip()
            lb_desc = (sw.get("loopback0_desc")
                       or lb_sec.get("description")
                       or "Switch MGMT / Router-ID").strip()
            if lb_ip:
                l3.append(
                    f"interface Loopback0\n"
                    f"description //{lb_desc}\n"
                    f"ip address {lb_ip} {lb_mask}\n"
                    f"exit"
                )

        rm_sec = l3_sections.get("routed_mgmt", {})
        if rm_sec.get("enabled"):
            rm_if = (rm_sec.get("interface") or "").strip()
            rm_ip = (sw.get("routed_mgmt_ip") or rm_sec.get("ip") or "").strip()
            rm_mask = (sw.get("routed_mgmt_mask")
                       or rm_sec.get("mask") or "").strip()
            rm_desc = (rm_sec.get("description") or "Routed Mgmt Uplink").strip()
            if rm_if and rm_ip and rm_mask:
                l3.append(
                    f"interface {rm_if}\n"
                    f"description //{rm_desc}\n"
                    f"no switchport\n"
                    f"ip address {rm_ip} {rm_mask}\n"
                    f"no shutdown\n"
                    f"exit"
                )

        svi_ips = sw.get("svi_ips", {}) or {}
        for svi in profile.get("svis", []) or []:
            vlan = (svi.get("vlan") or "").strip()
            if not vlan:
                continue
            per_sw = svi_ips.get(vlan, {}) or {}
            ip = (per_sw.get("ip") or "").strip()
            mask = (per_sw.get("mask") or "").strip()
            desc = (svi.get("description") or svi.get("name") or "").strip()
            helpers_raw = svi.get("helper_addresses") or ""
            if isinstance(helpers_raw, list):
                helpers = [h.strip() for h in helpers_raw if str(h).strip()]
            else:
                helpers = [h.strip() for h in str(helpers_raw).split(",")
                           if h.strip()]
            lines = [f"interface Vlan{vlan}"]
            if desc:
                lines.append(f"description //{desc}")
            if ip and mask:
                lines.append(f"ip address {ip} {mask}")
            else:
                lines.append("no ip address")
            for h in helpers:
                lines.append(f"ip helper-address {h}")
            lines.append("no shutdown")
            lines.append("exit")
            l3.append("\n".join(lines))

    # ── 3  Interfaces ───────────────────────────────────────────────────
    ifaces = []
    dis_tpl = base.get("disabled_port_template", "").strip()
    all_pgs = expand_port_groups_for_stack(
        model.get("port_groups", []), stack)
    if dis_tpl and all_pgs:
        rendered_dis = _r(dis_tpl)
        for pg in all_pgs:
            if pg.get("prefix", "").startswith("GigabitEthernet0/"):
                continue
            # expand the range and skip any individual port that is
            # claimed by a routed_uplink (those are emitted in the L3
            # Interfaces section as routed ports, not L2 access ports)
            single_ports = [
                f"{pg['prefix']}{i}"
                for i in range(pg["start"], pg["end"] + 1)
            ]
            # collapse consecutive kept ports back into ranges
            run_start = None
            run_end = None
            for i, p in zip(range(pg["start"], pg["end"] + 1), single_ports):
                if p in routed_iface_names:
                    if run_start is not None:
                        if run_start == run_end:
                            hdr = f"interface {pg['prefix']}{run_start}"
                        else:
                            hdr = (f"interface range {pg['prefix']}"
                                   f"{run_start}-{run_end}")
                        ifaces.append(f"{hdr}\n{rendered_dis}\nexit")
                        run_start = None
                    continue
                if run_start is None:
                    run_start = i
                run_end = i
            if run_start is not None:
                if run_start == run_end:
                    hdr = f"interface {pg['prefix']}{run_start}"
                else:
                    hdr = (f"interface range {pg['prefix']}"
                           f"{run_start}-{run_end}")
                ifaces.append(f"{hdr}\n{rendered_dis}\nexit")
    ifaces.append("interface vlan1\nno ip address\nshutdown\nexit")
    mgmt_port_pgs = [pg for pg in model.get("port_groups", [])
                     if pg.get("prefix", "").startswith("GigabitEthernet0/")]
    if mgmt_port_pgs:
        mgmt_assigned = any(
            pa.get("role") and pa["role"] != "unassigned"
            and "GigabitEthernet0/" in pa.get("interfaces", "")
            for pa in profile.get("port_assignments", [])
        )
        if not mgmt_assigned:
            pg = mgmt_port_pgs[0]
            iface = f"{pg['prefix']}{pg['start']}"
            oob_ip   = sw.get("oob_ip", "")
            oob_mask = sw.get("oob_mask", "")
            if oob_ip and oob_mask:
                ifaces.append(f"interface {iface}\n"
                              f"ip address {oob_ip} {oob_mask}\n"
                              f"negotiation auto\nexit")
            else:
                mgmt_cmds = base.get("mgmt_port", "").strip()
                if mgmt_cmds:
                    ifaces.append(f"interface {iface}\n{mgmt_cmds}")
    ospf_cfg = profile.get("ospf", {}) or {}
    ospf_pid_for_iface = (
        (str(ospf_cfg.get("process_id") or "1")).strip() or "1"
        if layer3 and ospf_cfg.get("enabled") else None
    )
    for pa in profile.get("port_assignments", []):
        if not pa.get("role") or pa["role"] == "unassigned":
            continue
        iface_name = pa.get("interfaces", "")
        role = roles.get(pa.get("role", ""), {})
        cmds = role.get("commands", "")
        # Build the Jinja context. L3 roles get ip/mask from the
        # per-switch routed_iface_ips dict so the same role template
        # works on every switch with site-specific IPs.
        ctx = dict(role_vars)
        ctx["description"] = pa.get("description", "")
        if role.get("requires_ip"):
            ip_info = routed_iface_ips.get(iface_name, {}) or {}
            ctx["ip"] = (ip_info.get("ip") or "").strip()
            ctx["mask"] = (ip_info.get("mask") or "").strip()
            if ospf_pid_for_iface:
                ctx.setdefault("ospf_pid", ospf_pid_for_iface)
        try:
            rendered = env.from_string(cmds).render(**ctx)
        except Exception as exc:
            rendered = (f"! ERROR rendering role '{pa.get('role','')}': {exc}\n"
                        f"{cmds}")
        ifaces.append(f"interface {iface_name}\n{rendered}\nexit")

    # ── 4  Management VLAN & Gateway ────────────────────────────────────
    # L2 profiles always emit a mgmt SVI from Step 1's Management IP /
    # Subnet Mask. L3 profiles emit a mgmt SVI only when the Management
    # VLAN section is enabled on the profile; the IP/mask come from the
    # per-switch fields if filled, falling back to the profile defaults.
    # ip default-gateway is always emitted when set - IOS uses it for
    # off-subnet mgmt traffic regardless of section layout.
    mgmt = []
    if not layer3:
        mgmt_vlan = profile.get("mgmt_vlan", "1")
        if sw.get("mgmt_ip") and sw.get("mgmt_mask"):
            mgmt.append(
                f"interface vlan{mgmt_vlan}\n"
                f"description //Switch MGMT\n"
                f"ip address {sw['mgmt_ip']} {sw['mgmt_mask']}\n"
                f"exit"
            )
    else:
        svi_sec = l3_sections.get("mgmt_svi", {})
        if svi_sec.get("enabled"):
            mgmt_vlan = (svi_sec.get("vlan")
                         or profile.get("mgmt_vlan") or "1").strip() or "1"
            svi_ip = (sw.get("mgmt_svi_ip")
                      or sw.get("mgmt_ip")
                      or svi_sec.get("ip") or "").strip()
            svi_mask = (sw.get("mgmt_svi_mask")
                        or sw.get("mgmt_mask")
                        or svi_sec.get("mask") or "").strip()
            svi_desc = (svi_sec.get("description") or "Switch MGMT").strip()
            if svi_ip and svi_mask:
                mgmt.append(
                    f"interface vlan{mgmt_vlan}\n"
                    f"description //{svi_desc}\n"
                    f"ip address {svi_ip} {svi_mask}\n"
                    f"exit"
                )
    if sw.get("default_gateway"):
        mgmt.append(f"ip default-gateway {sw['default_gateway']}")

    # ── 5  Post-Interface Custom Sections ────────────────────────────────
    post = []
    for cs in base.get("custom_sections", []):
        if cs.get("position") == "post-interface":
            cmds = cs.get("commands", "").strip()
            if cmds:
                post.append(_r(cmds))

    # Profile-defined ACLs (named, structured) - rendered after custom
    # sections so they sit in the post-interface block alongside other
    # site-wide policy.
    for acl in profile.get("acls", []) or []:
        rendered = _render_acl(acl)
        if rendered:
            post.append(rendered)

    # ── 5b  Routing (OSPF + static routes) ───────────────────────────────
    # OSPF process / networks / passive config come from the profile
    # (site-wide). Router-ID and static routes come from sw (per-switch).
    routing = []
    if layer3:
        ospf = profile.get("ospf", {}) or {}
        if ospf.get("enabled"):
            pid = (str(ospf.get("process_id") or "1")).strip() or "1"
            rid = ((sw.get("router_id") or "").strip()
                   or (sw.get("loopback0_ip") or "").strip())
            networks = ospf.get("networks", []) or []
            passive_default = bool(ospf.get("passive_default"))
            passive_ifaces = ospf.get("passive_interfaces", []) or []
            lines = [f"router ospf {pid}"]
            if rid:
                lines.append(f"router-id {rid}")
            if passive_default:
                lines.append("passive-interface default")
                # listed interfaces become exceptions (no passive-interface ...)
                for pi in passive_ifaces:
                    pi = str(pi).strip()
                    if pi:
                        lines.append(f"no passive-interface {pi}")
            else:
                for pi in passive_ifaces:
                    pi = str(pi).strip()
                    if pi:
                        lines.append(f"passive-interface {pi}")
            for n in networks:
                net = (n.get("network") or "").strip()
                wc = (n.get("wildcard") or "").strip()
                area = (str(n.get("area") or "0")).strip() or "0"
                if net and wc:
                    lines.append(f"network {net} {wc} area {area}")
            lines.append("exit")
            routing.append("\n".join(lines))

        bgp_block = _render_bgp(profile, sw)
        if bgp_block:
            routing.append(bgp_block)

        user_has_default_route = False
        for sr in sw.get("static_routes", []) or []:
            prefix = (sr.get("prefix") or "").strip()
            mask = (sr.get("mask") or "").strip()
            nh = (sr.get("next_hop") or "").strip()
            desc = (sr.get("description") or "").strip()
            if prefix and mask and nh:
                if prefix == "0.0.0.0" and mask == "0.0.0.0":
                    user_has_default_route = True
                line = f"ip route {prefix} {mask} {nh}"
                if desc:
                    line += f" name {desc.replace(' ', '_')}"
                routing.append(line)

        # Auto-generate a default route via the default gateway unless the
        # user already supplied one in static routes.
        dg = (sw.get("default_gateway") or "").strip()
        if dg and not user_has_default_route:
            routing.append(f"ip route 0.0.0.0 0.0.0.0 {dg}")

    # ── 6  Line Config ───────────────────────────────────────────────────
    lc = [base.get("line_config", "")]

    # ── 7  Banner / End ──────────────────────────────────────────────────
    bn = []
    banner = base.get("banner", "").strip()
    if banner:
        bn.append(f"banner login ^\n{banner}\n^")
    bn.append("end")

    return {
        "Global / Base":  build(gb),
        "VLANs":          build(vl),
        "L3 Interfaces":  build(l3),
        "Interfaces":     build(ifaces),
        "Management":     build(mgmt),
        "Post-Interface": build(post),
        "Routing":        build(routing),
        "Line Config":    build(lc),
        "Banner / End":   build(bn),
    }


def render_config(model, profile, roles, base, sw):
    """Build the full IOS config string from all parts.

    *model*    - switch model dict   (port_groups, provision)
    *profile*  - site profile dict   (vlan_definitions, role_variables,
                                      port_assignments, mgmt_vlan, and
                                      optionally layer3 / mgmt_style /
                                      loopback0 / svis / routed_uplinks /
                                      ospf / static_routes)
    *roles*    - all roles dict      {name: {commands: ...}}
    *base*     - base settings dict  (text-area sections)
    *sw*       - per-switch dict     (hostname, enable_secret, admin_password,
                                      domain_name, mgmt_ip, mgmt_mask,
                                      default_gateway)
    """
    sections = render_config_sections(model, profile, roles, base, sw)
    return "\n\n".join(s for s in sections.values() if s) + "\n"


# ===================================================================
#  TAB 1 - GENERATE CONFIG  (step-by-step wizard)
# ===================================================================
class GenerateTab(ttk.Frame):
    """Three-step wizard: Model & Site → Port Assignments → Switch Details."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_step = 0
        self.pa_rows = []          # port-assignment rows in step 2
        self._sections = {}        # populated after each generate
        self.l3_ip_rows = []       # routed-interface IP rows in step 3
        self.l3_static_rows = []   # static-route rows in step 3
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self):
        # ---- step indicator bar ----
        ind = ttk.Frame(self)
        ind.pack(fill="x", padx=10, pady=(10, 0))
        self.step_labels = []
        names = ["Model & Site", "Port Assignments", "Switch Details"]
        for i, name in enumerate(names):
            if i > 0:
                ttk.Label(ind, text="  \u25b8  ",
                          style="StepArrow.TLabel").pack(side="left")
            lbl = ttk.Label(ind, text=f"  {i + 1}. {name}  ")
            lbl.pack(side="left")
            self.step_labels.append(lbl)
        ttk.Separator(self).pack(fill="x", padx=5, pady=(8, 0))

        # ---- step container ----
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.step_frames = []
        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._show_step(0)

    # ---- step indicator helpers ----
    def _update_indicator(self):
        for i, lbl in enumerate(self.step_labels):
            if i < self.current_step:
                lbl.configure(style="StepDone.TLabel")
            elif i == self.current_step:
                lbl.configure(style="StepActive.TLabel")
            else:
                lbl.configure(style="StepPending.TLabel")

    def _show_step(self, n):
        for f in self.step_frames:
            f.pack_forget()
        self.current_step = n
        self.step_frames[n].pack(fill="both", expand=True)
        self._update_indicator()

    # ============================================================ Step 1
    def _build_step1(self):
        frame = ttk.Frame(self.container)
        self.step_frames.append(frame)

        scroll = ScrollFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        # spacer to push content toward vertical center
        ttk.Frame(body).pack(pady=40)

        center = ttk.Frame(body)
        center.pack(anchor="center")

        ttk.Label(center, text="Step 1 - Select Model & Site Profile",
                  style="Sec.TLabel").pack(pady=(0, 20))

        self.model_cb = _combo(center, "Switch Model",
                               list(self.app.models.keys()))
        self.profile_cb = _combo(center, "Site Profile",
                                 list(self.app.profiles.keys()))

        ttk.Label(center,
                  text="The model determines available interfaces.\n"
                       "The profile provides VLAN and role defaults.",
                  style="Hint.TLabel").pack(pady=(12, 0))

        bf = ttk.Frame(center)
        bf.pack(pady=20)
        ttk.Button(bf, text="Next  \u25b6",
                   command=self._step1_next).pack()

    # ============================================================ Step 2
    def _build_step2(self):
        frame = ttk.Frame(self.container)
        self.step_frames.append(frame)

        # navigation - pack at bottom first so it's always visible
        nav = ttk.Frame(frame)
        nav.pack(side="bottom", fill="x", padx=10, pady=8)
        ttk.Button(nav, text="\u25c0  Back",
                   command=lambda: self._show_step(0)).pack(side="left")
        ttk.Button(nav, text="Next  \u25b6",
                   command=self._step2_next).pack(side="right")

        # scrollable content area above the pinned nav
        scroll = ScrollFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        # reference: model port groups
        ref_lf = ttk.LabelFrame(body,
                                text="Available Interfaces (from model)",
                                padding=8)
        ref_lf.pack(fill="x", padx=10, pady=(8, 4))
        self.port_ref = ttk.Label(ref_lf, text="", foreground=C["fg"])
        self.port_ref.pack(anchor="w")

        ttk.Label(body, style="Hint.TLabel",
                  text="  Assign roles to the interface ranges you need.  "
                       "Any range not listed stays disabled automatically."
                  ).pack(anchor="w", padx=10, pady=(4, 2))

        # port display mode toggle
        mode_fr = ttk.Frame(body)
        mode_fr.pack(fill="x", padx=10, pady=(4, 2))
        ttk.Label(mode_fr, text="Port Display:").pack(side="left")
        self.pa_display_cb = ttk.Combobox(
            mode_fr, width=18, state="readonly",
            values=["Range", "Individual Ports"])
        self.pa_display_cb.bind("<MouseWheel>", lambda _e: "break")
        self.pa_display_cb.pack(side="left", padx=6)
        cur = resolve_base(self.app.base).get("port_display_mode", "listed")
        self.pa_display_cb.set(
            "Range" if cur == "range" else "Individual Ports")
        self.pa_display_cb.bind("<<ComboboxSelected>>",
                                lambda _e: self._on_display_mode_changed())

        # port assignment table
        pa_lf = ttk.LabelFrame(body, text="Port Assignments", padding=5)
        pa_lf.pack(fill="x", padx=10, pady=(0, 5))

        self.pa_table = ttk.Frame(pa_lf)
        self.pa_table.pack(fill="x")
        self.pa_table.columnconfigure(0, weight=0)
        self.pa_table.columnconfigure(1, weight=0)
        self.pa_table.columnconfigure(2, weight=1)
        self.pa_table.columnconfigure(3, weight=0)

        ttk.Label(self.pa_table, text="Interface(s)").grid(
            row=0, column=0, sticky="w", padx=1)
        ttk.Label(self.pa_table, text="Role").grid(
            row=0, column=1, sticky="w", padx=1)
        ttk.Label(self.pa_table, text="Description").grid(
            row=0, column=2, sticky="w", padx=1)
        ttk.Button(self.pa_table, text="+ Add Row",
                   command=lambda: self._add_pa_row()).grid(
            row=0, column=3, sticky="e", padx=2)

        self.pa_next_row = 1
        self.pa_container = self.pa_table

    # ============================================================ Step 3
    def _build_step3(self):
        frame = ttk.Frame(self.container)
        self.step_frames.append(frame)

        # navigation - pack at bottom first so it's always visible
        nav = ttk.Frame(frame)
        nav.pack(side="bottom", fill="x", padx=10, pady=8)
        ttk.Button(nav, text="\u25c0  Back",
                   command=self._step3_back).pack(side="left")
        ttk.Button(nav, text="Generate Config",
                   command=self._generate).pack(side="left", padx=10)
        ttk.Button(nav, text="Copy to Clipboard",
                   command=self._copy).pack(side="left", padx=4)
        ttk.Button(nav, text="Save to File",
                   command=self._save).pack(side="left", padx=4)

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        self._step3_paned = paned

        # -- left: form --
        left = ScrollFrame(paned)
        paned.add(left, weight=3)
        form = left.inner

        ttk.Label(form, text="Step 3 - Enter Per-Switch Details",
                  style="Sec.TLabel").pack(anchor="w", padx=5, pady=(5, 10))

        self.hostname    = _field(form, "Hostname")
        self.username    = _field(form, "Local Username")
        self.secret      = _field(form, "Enable Secret")
        self.password    = _field(form, "Admin Password")
        self.domain      = _field(form, "Domain Name")
        self.mgmt_ip     = _field(form, "Management IP")
        self.mgmt_mask   = _field(form, "Subnet Mask", "255.255.255.0")
        self.gateway     = _field(form, "Default Gateway")
        self.work_order  = _field(form, "Work Order #")
        # Cache the label widget that sits next to each L3-aware entry so
        # we can rename it when an L3 profile is selected
        self._mgmt_ip_label  = self.mgmt_ip.master.winfo_children()[0]
        self._mgmt_mask_label = self.mgmt_mask.master.winfo_children()[0]
        self._gateway_label  = self.gateway.master.winfo_children()[0]

        # OOB management port (Gi0/0) - only shown for models that have one
        self.oob_frame = ttk.Frame(form)
        _section(self.oob_frame, "OOB Management Port (Gi0/0)")
        ttk.Label(self.oob_frame,
                  text="Optional - leave blank to use base settings default.",
                  style="Hint.TLabel").pack(anchor="w", padx=5, pady=(2, 0))
        self.oob_ip   = _field(self.oob_frame, "OOB IP Address")
        self.oob_mask = _field(self.oob_frame, "OOB Subnet Mask")

        # Layer 3 Details (only shown when the selected profile is L3)
        self.l3_frame = ttk.Frame(form)
        _section(self.l3_frame, "Layer 3 Details")
        ttk.Label(self.l3_frame,
                  text="Per-switch L3 values. SVIs and OSPF networks come\n"
                       "from the profile.",
                  style="Hint.TLabel").pack(anchor="w", padx=5, pady=(2, 4))

        # Loopback0
        self.lb_lf = ttk.LabelFrame(self.l3_frame, text="Loopback0", padding=5)
        self.lb_lf.pack(fill="x", padx=5, pady=4)
        self.lb_ip   = _field(self.lb_lf, "IP")
        self.lb_mask = _field(self.lb_lf, "Mask", "255.255.255.255")
        self.lb_desc = _field(self.lb_lf, "Description",
                              "Switch MGMT / Router-ID")

        # Routed Mgmt Interface (the interface name and description come
        # from the profile; IP / Mask are per-switch). Title is updated
        # in _apply_l3_visibility to include the interface name.
        self.rm_lf = ttk.LabelFrame(self.l3_frame, text="Routed Interface",
                                    padding=5)
        self.rm_lf.pack(fill="x", padx=5, pady=4)
        self.rm_ip   = _field(self.rm_lf, "IP")
        self.rm_mask = _field(self.rm_lf, "Mask")

        # Management VLAN SVI (VLAN ID and description come from the
        # profile; IP / Mask are per-switch). Title is updated in
        # _apply_l3_visibility to include the VLAN number.
        self.msvi_lf = ttk.LabelFrame(self.l3_frame, text="Management VLAN",
                                      padding=5)
        self.msvi_lf.pack(fill="x", padx=5, pady=4)
        self.msvi_ip   = _field(self.msvi_lf, "IP")
        self.msvi_mask = _field(self.msvi_lf, "Mask")

        # Router ID (defaults to Loopback0 IP if blank). Shown only when
        # the profile has OSPF enabled.
        self.rid_lf = ttk.LabelFrame(self.l3_frame, text="OSPF Router ID",
                                     padding=5)
        self.rid_lf.pack(fill="x", padx=5, pady=4)
        self.router_id = _field(self.rid_lf, "Router ID")
        ttk.Label(self.rid_lf, style="Hint.TLabel",
                  text="  Leave blank to default to the Loopback0 IP."
                  ).pack(anchor="w", padx=2, pady=(0, 2))

        # Per-routed-interface IP grid (auto-populated from Step 2)
        self.l3_ip_lf = ttk.LabelFrame(
            self.l3_frame, text="Routed Interface IPs", padding=5)
        self.l3_ip_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.l3_ip_lf, style="Hint.TLabel",
                  text="  One row per port assigned to a role with\n"
                       "  'Requires per-switch IP' on. Populated from Step 2."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        ih = ttk.Frame(self.l3_ip_lf); ih.pack(fill="x")
        ih.columnconfigure(0, weight=2, uniform="l3ip")
        ih.columnconfigure(1, weight=1, uniform="l3ip")
        ih.columnconfigure(2, weight=1, uniform="l3ip")
        ttk.Label(ih, text="Interface", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(ih, text="IP", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(ih, text="Mask", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        self.l3_ip_frame = ttk.Frame(self.l3_ip_lf)
        self.l3_ip_frame.pack(fill="x")

        # Per-SVI IPs (auto-populated from profile.svis)
        self.svi_ip_lf = ttk.LabelFrame(
            self.l3_frame, text="SVI IPs", padding=5)
        self.svi_ip_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.svi_ip_lf, style="Hint.TLabel",
                  text="  One row per SVI defined in the profile. IP /\n"
                       "  Mask pre-fill from the profile when set;\n"
                       "  override here for per-switch values."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        sih = ttk.Frame(self.svi_ip_lf); sih.pack(fill="x")
        sih.columnconfigure(0, weight=2, uniform="sviip")
        sih.columnconfigure(1, weight=1, uniform="sviip")
        sih.columnconfigure(2, weight=1, uniform="sviip")
        ttk.Label(sih, text="VLAN", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(sih, text="IP", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(sih, text="Mask", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        self.svi_ip_frame = ttk.Frame(self.svi_ip_lf)
        self.svi_ip_frame.pack(fill="x")
        self.svi_ip_rows = []

        # Static routes
        self.l3_static_lf = ttk.LabelFrame(
            self.l3_frame, text="Static Routes", padding=5)
        self.l3_static_lf.pack(fill="x", padx=5, pady=4)
        sh = ttk.Frame(self.l3_static_lf); sh.pack(fill="x")
        for col in range(4):
            sh.columnconfigure(col, weight=1, uniform="l3sr")
        ttk.Label(sh, text="Prefix", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(sh, text="Mask", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(sh, text="Next Hop", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Label(sh, text="Description", anchor="w").grid(
            row=0, column=3, sticky="ew", padx=1)
        ttk.Button(sh, text="+ Add Route",
                   command=self._add_l3_static).grid(
                       row=0, column=4, padx=(6, 1))
        self.l3_static_frame = ttk.Frame(self.l3_static_lf)
        self.l3_static_frame.pack(fill="x")
        # Preview of the actual 'ip route' lines this step will emit,
        # including the auto default route from the Default Gateway field.
        ttk.Label(self.l3_static_lf, style="Hint.TLabel",
                  text="  Preview - lines that will be generated:"
                  ).pack(anchor="w", padx=2, pady=(6, 0))
        self.l3_static_preview = tk.Text(
            self.l3_static_lf, height=4, wrap="none",
            font=("Consolas", 9),
            bg=C["bg_input"], fg=C["green"],
            relief="flat", bd=2, state="disabled")
        self.l3_static_preview.pack(fill="x", padx=2, pady=(0, 2))
        _attach_context_menu(self.l3_static_preview)
        # Re-render preview whenever the Default Gateway changes.
        self.gateway.bind("<KeyRelease>",
                          lambda _e: self._refresh_static_preview(),
                          add="+")

        # BGP per-switch values - one block per profile BGP instance
        self.bgp_lf = ttk.LabelFrame(self.l3_frame, text="BGP", padding=5)
        self.bgp_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.bgp_lf, style="Hint.TLabel",
                  text="  Per-switch ISP/User values + peers unique to this\n"
                       "  switch. One block per BGP instance defined in the\n"
                       "  site profile."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        self.bgp_inst_container = ttk.Frame(self.bgp_lf)
        self.bgp_inst_container.pack(fill="x")
        # Each entry: dict with isp_gateway / user_network / user_mask /
        # circuit_id Entries, plus a list of peer row dicts and the frame
        # the block is packed into. Built dynamically when a BGP-enabled
        # profile is selected. The ISP-facing IP now comes from the SVI
        # for the ISP VLAN (entered in the SVI IPs section).
        self.bgp_inst_blocks = []

        # -- right: preview --
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        ttk.Label(right, text="Config Preview",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=(4, 0))

        # quick-copy toolbar
        qc_fr = ttk.Frame(right)
        qc_fr.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(qc_fr, text="Copy section:",
                  style="Hint.TLabel").grid(row=0, column=0, padx=(0, 4))
        self._qc_buttons = {}
        _qc_sec_names = ("Global / Base", "VLANs", "L3 Interfaces",
                         "Interfaces", "Management", "Routing",
                         "Line Config", "Banner / End")
        for _col, _sec_name in enumerate(_qc_sec_names, start=1):
            qc_fr.columnconfigure(_col, weight=1, uniform="qcbtn")
            btn = ttk.Button(
                qc_fr, text=_sec_name, state="disabled",
                command=lambda n=_sec_name: self._copy_section(n))
            btn.grid(row=0, column=_col, padx=2, sticky="ew")
            self._qc_buttons[_sec_name] = btn

        self.preview = scrolledtext.ScrolledText(
            right, wrap="none", font=("Consolas", 10),
            bg=C["bg_input"], fg=C["green"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2,
            state="disabled")
        self.preview.pack(fill="both", expand=True, padx=4, pady=4)
        _attach_context_menu(self.preview)

        # Snap the sash to ~60% of total width on first layout so the
        # form pane starts wide enough for the L3 grids to fit.
        self._step3_sash_set = False
        self._step3_paned.bind("<Configure>", self._step3_size_sash)

    def _step3_size_sash(self, event):
        if self._step3_sash_set:
            return
        try:
            total = event.width
            if total > 100:
                self._step3_paned.sashpos(0, int(total * 0.60))
                self._step3_sash_set = True
        except Exception:
            pass

    # --------------------------------------------------------- step logic
    def _step1_next(self):
        mn = self.model_cb.get()
        pn = self.profile_cb.get()
        if not mn or mn not in self.app.models:
            _dialog("Missing", "Select a switch model.", "warning")
            return
        if not pn or pn not in self.app.profiles:
            _dialog("Missing", "Select a site profile.", "warning")
            return
        self._populate_step2(mn, pn)
        # auto-fill from profile defaults - values stay editable, edits
        # are per-switch and never written back to the profile.
        profile = self.app.profiles[pn]
        domain = profile.get("domain_name", "")
        if domain:
            self.domain.delete(0, "end")
            self.domain.insert(0, domain)
        creds = profile.get("credentials", {}) or {}
        for entry, key in ((self.username, "local_username"),
                           (self.password, "admin_password"),
                           (self.secret,   "enable_secret")):
            val = creds.get(key, "")
            if val:
                entry.delete(0, "end")
                entry.insert(0, val)
        # Show/hide L3 details and relabel gateway based on profile settings
        self._apply_l3_visibility(profile)
        # show/hide OOB fields based on whether model has Gi0/0
        model = self.app.models[mn]
        has_oob = any(pg.get("prefix", "").startswith("GigabitEthernet0/")
                      for pg in model.get("port_groups", []))
        if has_oob:
            self.oob_frame.pack(fill="x", padx=5, pady=2)
        else:
            self.oob_frame.pack_forget()
            self.oob_ip.delete(0, "end")
            self.oob_mask.delete(0, "end")
        self._show_step(1)

    def _populate_step2(self, model_name, profile_name):
        model   = self.app.models[model_name]
        profile = self.app.profiles[profile_name]

        # expand port groups for stack members
        stack = model.get("stack_members", 1)
        all_pgs = expand_port_groups_for_stack(
            model.get("port_groups", []), stack)

        # update reference label - group similar port types onto one line
        # e.g. GigabitEthernet1/0/1–24 .. GigabitEthernet4/0/1–24
        #   → GigabitEthernet[1-4]/0/1 – 24
        groups = {}  # (name_part, tail, start, end) → [member_nums]
        ungrouped = []
        for pg in all_pgs:
            m = re.match(r'^([A-Za-z-]*)(\d+)(/.*)$', pg["prefix"])
            if m and stack > 1:
                key = (m.group(1), m.group(3), pg["start"], pg["end"])
                groups.setdefault(key, []).append(int(m.group(2)))
            else:
                ungrouped.append(pg)
        lines = []
        for (name_part, tail, s, e), members in groups.items():
            members.sort()
            if len(members) > 1:
                tag = f"{name_part}[{members[0]}-{members[-1]}]{tail}"
            else:
                tag = f"{name_part}{members[0]}{tail}"
            lines.append(f"  {tag}{s} \u2013 {e}" if s != e
                         else f"  {tag}{s}")
        for pg in ungrouped:
            lines.append(f"  {pg['prefix']}{pg['start']} \u2013 {pg['end']}"
                         if pg["start"] != pg["end"]
                         else f"  {pg['prefix']}{pg['start']}")
        self.port_ref.configure(
            text="\n".join(lines) if lines else "(no port groups defined)")

        # clear and repopulate
        self._clear_pa_rows()
        listed = self.pa_display_cb.get() == "Individual Ports"
        pa_list = profile.get("port_assignments", [])
        if pa_list:
            # profile already has assignments - use them
            for pa in pa_list:
                if listed:
                    for iface in expand_range_iface(pa.get("interfaces", "")):
                        self._add_pa_row({"interfaces": iface,
                                          "role": pa.get("role", ""),
                                          "description": pa.get(
                                              "description", "")})
                else:
                    self._add_pa_row(pa)
        else:
            # no profile assignments - seed from model port groups
            for pg in all_pgs:
                if pg["start"] == pg["end"] or listed:
                    if listed and pg["start"] != pg["end"]:
                        for i in range(pg["start"], pg["end"] + 1):
                            self._add_pa_row(
                                {"interfaces": f"{pg['prefix']}{i}",
                                 "role": "", "description": ""})
                    else:
                        self._add_pa_row(
                            {"interfaces": f"{pg['prefix']}{pg['start']}",
                             "role": "", "description": ""})
                else:
                    iface = (f"range {pg['prefix']}"
                             f"{pg['start']}-{pg['end']}")
                    self._add_pa_row({"interfaces": iface,
                                      "role": "", "description": ""})

    def _step2_next(self):
        # Re-sync the L3 IP grid in case the user changed port assignments
        # in Step 2 since the last visit.
        pn = self.profile_cb.get()
        if pn and pn in self.app.profiles:
            profile = self.app.profiles[pn]
            if profile.get("layer3"):
                self._populate_l3_ip_rows()
        self._show_step(2)

    def _step3_back(self):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.configure(state="disabled")
        self._sections = {}
        for btn in self._qc_buttons.values():
            btn.configure(state="disabled")
        self._show_step(1)

    def _on_display_mode_changed(self):
        """Re-populate port assignment rows when the user toggles the
        port display mode between Range and Individual Ports."""
        mn = self.model_cb.get()
        pn = self.profile_cb.get()
        if mn and mn in self.app.models and pn and pn in self.app.profiles:
            self._populate_step2(mn, pn)

    # ------------------------------------------------ port-assignment rows
    def _add_pa_row(self, data=None):
        r = self.pa_next_row
        self.pa_next_row += 1
        iface = ttk.Entry(self.pa_container, width=36)
        iface.grid(row=r, column=0, sticky="w", padx=1, pady=1)
        _attach_context_menu(iface)
        role = ttk.Combobox(self.pa_container, width=24, state="readonly",
                            values=["unassigned"] + list(self.app.roles.keys()))
        role.bind("<MouseWheel>", lambda _e: "break")
        role.grid(row=r, column=1, sticky="w", padx=1, pady=1)
        desc = ttk.Entry(self.pa_container, width=14)
        desc.grid(row=r, column=2, sticky="ew", padx=1, pady=1)
        _attach_context_menu(desc)
        del_btn = ttk.Button(self.pa_container, text="X", width=3,
                             style="Del.TButton",
                             command=lambda: self._del_pa_row(r))
        del_btn.grid(row=r, column=3, padx=2, pady=1)
        if data:
            iface.insert(0, data.get("interfaces", ""))
            role.set(data.get("role") or "unassigned")
            desc.insert(0, data.get("description", ""))
        self.pa_rows.append({"grid_row": r, "iface": iface,
                             "role": role, "desc": desc,
                             "widgets": [iface, role, desc, del_btn]})

    def _del_pa_row(self, grid_row):
        for r in self.pa_rows:
            if r["grid_row"] == grid_row:
                for w in r["widgets"]:
                    w.destroy()
                break
        self.pa_rows = [r for r in self.pa_rows if r["grid_row"] != grid_row]

    def _clear_pa_rows(self):
        for r in self.pa_rows:
            for w in r["widgets"]:
                w.destroy()
        self.pa_rows.clear()
        self.pa_next_row = 1

    # ------------------------------------------------------------ actions
    def refresh_combos(self):
        self.model_cb["values"]   = list(self.app.models.keys())
        self.profile_cb["values"] = list(self.app.profiles.keys())

    def _apply_l3_visibility(self, profile):
        """Show/hide the Layer 3 Details frame and its sub-sections
        based on the profile's layer3 flag, the three l3_sections
        enable flags (loopback / routed_mgmt / mgmt_svi), and
        ospf.enabled. Pre-fills each section's IP / Mask from the
        profile when the per-switch field is blank. Default Gateway is
        always editable - it's required on every device."""
        layer3 = bool(profile.get("layer3", False))
        sections = _normalize_l3_sections(profile) if layer3 else {}
        ospf_enabled = bool((profile.get("ospf") or {}).get("enabled", False))

        self._gateway_label.configure(text="Default Gateway")
        self.gateway.configure(state="normal")

        # Step 1's Management IP / Subnet Mask are L2-only. L3 profiles
        # source the mgmt IP from one of the three l3_sections instead.
        mgmt_ip_row = self.mgmt_ip.master
        mgmt_mask_row = self.mgmt_mask.master
        if layer3:
            mgmt_ip_row.pack_forget()
            mgmt_mask_row.pack_forget()
        else:
            if not mgmt_ip_row.winfo_ismapped():
                mgmt_ip_row.pack(fill="x", padx=5, pady=2,
                                 before=self.gateway.master)
            if not mgmt_mask_row.winfo_ismapped():
                mgmt_mask_row.pack(fill="x", padx=5, pady=2,
                                   before=self.gateway.master)

        if not layer3:
            self.l3_frame.pack_forget()
            self._clear_l3_ip_rows()
            self._clear_svi_ip_rows()
            self._clear_l3_statics()
            self._clear_bgp_inst_blocks()
            return

        # L3 frame is on. Hide everything first, then re-pack the
        # sub-sections in their original top-to-bottom order so the
        # layout stays consistent regardless of which combination of
        # sections / ospf_enabled we end up with.
        self.l3_frame.pack(fill="x", padx=5, pady=2)
        for sub in (self.lb_lf, self.rm_lf, self.msvi_lf, self.rid_lf,
                    self.l3_ip_lf, self.svi_ip_lf, self.l3_static_lf,
                    self.bgp_lf):
            sub.pack_forget()

        # Loopback0 section.
        lb_sec = sections.get("loopback", {})
        if lb_sec.get("enabled"):
            self.lb_lf.pack(fill="x", padx=5, pady=4)
            default_mask = (lb_sec.get("mask") or "255.255.255.255").strip()
            if not self.lb_mask.get().strip() and default_mask:
                self.lb_mask.delete(0, "end")
                self.lb_mask.insert(0, default_mask)
            default_ip = (lb_sec.get("ip") or "").strip()
            if not self.lb_ip.get().strip() and default_ip:
                self.lb_ip.insert(0, default_ip)
            default_desc = (lb_sec.get("description") or "").strip()
            if not self.lb_desc.get().strip() and default_desc:
                self.lb_desc.insert(0, default_desc)

        # Routed Mgmt Interface section.
        rm_sec = sections.get("routed_mgmt", {})
        if rm_sec.get("enabled"):
            rm_if = (rm_sec.get("interface") or "").strip()
            title = f"Routed Interface ({rm_if})" if rm_if else "Routed Interface"
            self.rm_lf.configure(text=title)
            self.rm_lf.pack(fill="x", padx=5, pady=4)
            default_mask = (rm_sec.get("mask") or "").strip()
            if not self.rm_mask.get().strip() and default_mask:
                self.rm_mask.insert(0, default_mask)
            default_ip = (rm_sec.get("ip") or "").strip()
            if not self.rm_ip.get().strip() and default_ip:
                self.rm_ip.insert(0, default_ip)

        # Management VLAN SVI section.
        svi_sec = sections.get("mgmt_svi", {})
        if svi_sec.get("enabled"):
            vlan = (svi_sec.get("vlan") or "").strip()
            title = f"Management VLAN {vlan}" if vlan else "Management VLAN"
            self.msvi_lf.configure(text=title)
            self.msvi_lf.pack(fill="x", padx=5, pady=4)
            default_mask = (svi_sec.get("mask") or "").strip()
            if not self.msvi_mask.get().strip() and default_mask:
                self.msvi_mask.insert(0, default_mask)
            default_ip = (svi_sec.get("ip") or "").strip()
            if not self.msvi_ip.get().strip() and default_ip:
                self.msvi_ip.insert(0, default_ip)

        # Router ID only relevant when OSPF is enabled in the profile.
        if ospf_enabled:
            self.rid_lf.pack(fill="x", padx=5, pady=4)

        # Routed Interface IPs only when at least one Step 2 port is
        # assigned to a role with requires_ip=True. Populate first so we
        # can read the row count, then decide whether to show the section.
        self._populate_l3_ip_rows()
        if self.l3_ip_rows:
            self.l3_ip_lf.pack(fill="x", padx=5, pady=4)

        # SVI IPs section only when the profile actually defines SVIs.
        if profile.get("svis"):
            self.svi_ip_lf.pack(fill="x", padx=5, pady=4)
            self._populate_svi_ip_rows(profile)
        else:
            self._clear_svi_ip_rows()

        self.l3_static_lf.pack(fill="x", padx=5, pady=4)

        bgp_instances = (profile.get("bgp") or {}).get("instances") or []
        if bgp_instances:
            self.bgp_lf.pack(fill="x", padx=5, pady=4)
            self._populate_bgp_inst_blocks(bgp_instances)
        else:
            self._clear_bgp_inst_blocks()

        self._refresh_static_preview()

    def _clear_l3_ip_rows(self):
        for r in self.l3_ip_rows:
            r["frame"].destroy()
        self.l3_ip_rows.clear()

    def _populate_l3_ip_rows(self):
        """Walk the current Step 2 port assignments and create one row
        in the Routed Interface IPs grid for each port assigned to a
        role with requires_ip=True. Preserves any IPs the user already
        typed for the same interface. Pre-fills the Mask column from
        the profile's default_routed_mask when the user hasn't typed
        one for that interface yet."""
        existing = {r["iface_name"]: (r["ip"].get(), r["mask"].get())
                    for r in self.l3_ip_rows}
        self._clear_l3_ip_rows()
        pn = self.profile_cb.get()
        profile = self.app.profiles.get(pn, {}) or {}
        default_mask = (profile.get("default_routed_mask") or "").strip()
        for r in self.pa_rows:
            iface = r["iface"].get().strip()
            role_name = r["role"].get() or ""
            if not iface or role_name == "unassigned":
                continue
            role = self.app.roles.get(role_name, {}) or {}
            if not role.get("requires_ip"):
                continue
            row = ttk.Frame(self.l3_ip_frame); row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=2, uniform="l3ip")
            row.columnconfigure(1, weight=1, uniform="l3ip")
            row.columnconfigure(2, weight=1, uniform="l3ip")
            ttk.Label(row, text=iface, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=1)
            ip = ttk.Entry(row); ip.grid(row=0, column=1, sticky="ew", padx=1)
            mask = ttk.Entry(row); mask.grid(row=0, column=2, sticky="ew", padx=1)
            _attach_context_menu(ip)
            _attach_context_menu(mask)
            if iface in existing:
                ip.insert(0, existing[iface][0])
                mask.insert(0, existing[iface][1])
            if not mask.get() and default_mask:
                mask.insert(0, default_mask)
            self.l3_ip_rows.append({"frame": row, "iface_name": iface,
                                    "ip": ip, "mask": mask})

    def _clear_svi_ip_rows(self):
        for r in self.svi_ip_rows:
            r["frame"].destroy()
        self.svi_ip_rows.clear()

    def _populate_svi_ip_rows(self, profile):
        """One row per SVI defined in the profile. Preserves any IPs
        the user already typed for the same VLAN. Pre-fills IP / Mask
        from profile.svis[].ip / .mask when the user hasn't typed a
        per-switch value yet (typical workflow: profile sets the mask
        site-wide, optionally a default IP)."""
        existing = {r["vlan"]: (r["ip"].get(), r["mask"].get())
                    for r in self.svi_ip_rows}
        self._clear_svi_ip_rows()
        for svi in profile.get("svis", []) or []:
            vlan = (svi.get("vlan") or "").strip()
            if not vlan:
                continue
            desc = (svi.get("description") or "").strip()
            label = f"Vlan{vlan}" + (f" - {desc}" if desc else "")
            default_ip = (svi.get("ip") or "").strip()
            default_mask = (svi.get("mask") or "").strip()
            row = ttk.Frame(self.svi_ip_frame); row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=2, uniform="sviip")
            row.columnconfigure(1, weight=1, uniform="sviip")
            row.columnconfigure(2, weight=1, uniform="sviip")
            ttk.Label(row, text=label, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=1)
            ip = ttk.Entry(row); ip.grid(row=0, column=1, sticky="ew", padx=1)
            mask = ttk.Entry(row); mask.grid(row=0, column=2, sticky="ew", padx=1)
            _attach_context_menu(ip)
            _attach_context_menu(mask)
            if vlan in existing:
                ip.insert(0, existing[vlan][0])
                mask.insert(0, existing[vlan][1])
            if not ip.get() and default_ip:
                ip.insert(0, default_ip)
            if not mask.get() and default_mask:
                mask.insert(0, default_mask)
            self.svi_ip_rows.append({"frame": row, "vlan": vlan,
                                     "ip": ip, "mask": mask})

    def _clear_l3_statics(self):
        for r in self.l3_static_rows:
            r["frame"].destroy()
        self.l3_static_rows.clear()

    def _add_l3_static(self, data=None):
        row = ttk.Frame(self.l3_static_frame); row.pack(fill="x", pady=1)
        for col in range(4):
            row.columnconfigure(col, weight=1, uniform="l3sr")
        prefix = ttk.Entry(row); prefix.grid(row=0, column=0, sticky="ew", padx=1)
        mask   = ttk.Entry(row); mask.grid(row=0, column=1, sticky="ew", padx=1)
        nh     = ttk.Entry(row); nh.grid(row=0, column=2, sticky="ew", padx=1)
        desc   = ttk.Entry(row); desc.grid(row=0, column=3, sticky="ew", padx=1)
        for w in (prefix, mask, nh, desc):
            _attach_context_menu(w)
            w.bind("<KeyRelease>",
                   lambda _e: self._refresh_static_preview(), add="+")
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_l3_static(row)
                   ).grid(row=0, column=4, padx=(6, 1))
        if data:
            prefix.insert(0, data.get("prefix", ""))
            mask.insert(0, data.get("mask", ""))
            nh.insert(0, data.get("next_hop", ""))
            desc.insert(0, data.get("description", ""))
        self.l3_static_rows.append({"frame": row, "prefix": prefix,
                                    "mask": mask, "nh": nh, "desc": desc})
        self._refresh_static_preview()

    def _del_l3_static(self, frame):
        self.l3_static_rows[:] = [r for r in self.l3_static_rows
                                  if r["frame"] is not frame]
        frame.destroy()
        self._refresh_static_preview()

    def _refresh_static_preview(self):
        """Update the Static Routes preview pane with the exact 'ip route'
        lines the renderer will emit: user-entered routes plus the auto
        default route from Default Gateway (unless the user already typed
        a 0.0.0.0/0 entry)."""
        if not hasattr(self, "l3_static_preview"):
            return
        lines = []
        user_has_default = False
        for r in getattr(self, "l3_static_rows", []):
            prefix = r["prefix"].get().strip()
            mask = r["mask"].get().strip()
            nh = r["nh"].get().strip()
            desc = r["desc"].get().strip()
            if not (prefix and mask and nh):
                continue
            if prefix == "0.0.0.0" and mask == "0.0.0.0":
                user_has_default = True
            line = f"ip route {prefix} {mask} {nh}"
            if desc:
                line += f" name {desc.replace(' ', '_')}"
            lines.append(line)
        dg = self.gateway.get().strip() if hasattr(self, "gateway") else ""
        if dg and not user_has_default:
            lines.append(f"ip route 0.0.0.0 0.0.0.0 {dg}    ! auto from Default Gateway")
        if not lines:
            lines = ["! No static routes will be generated."]
        self.l3_static_preview.configure(state="normal")
        self.l3_static_preview.delete("1.0", "end")
        self.l3_static_preview.insert("1.0", "\n".join(lines))
        self.l3_static_preview.configure(state="disabled")

    # -- per-instance BGP blocks in Step 3 --
    def _clear_bgp_inst_blocks(self):
        for blk in self.bgp_inst_blocks:
            blk["frame"].destroy()
        self.bgp_inst_blocks.clear()

    def _populate_bgp_inst_blocks(self, profile_instances):
        """Rebuild one Step 3 BGP block per profile instance, preserving
        any values already typed for instances that still exist (keyed
        by local ASN). Peer slots come from the profile; per-switch
        Peer IP and Password are entered in Step 3."""
        existing = {}
        for blk in self.bgp_inst_blocks:
            key = blk["local_asn"]
            existing[key] = self._snapshot_bgp_inst_block(blk)
        self._clear_bgp_inst_blocks()
        for inst in profile_instances:
            local_asn = str(inst.get("local_asn") or "").strip()
            if not local_asn:
                continue
            # Tolerate older profiles that used "peers" with full info;
            # treat them as slots by dropping ip/password fields.
            slots = inst.get("slots")
            if slots is None:
                slots = [{"peer_asn": p.get("peer_asn"),
                          "description": p.get("description")}
                         for p in (inst.get("peers") or [])]
            self._add_bgp_inst_block(
                local_asn,
                str(inst.get("peer_asn") or "").strip(),
                slots,
                existing.get(local_asn),
            )

    def _snapshot_bgp_inst_block(self, blk):
        return {
            "isp_gateway":  blk["isp_gateway"].get(),
            "user_network": blk["user_network"].get(),
            "user_mask":    blk["user_mask"].get(),
            "circuit_id":   blk["circuit_id"].get(),
            "peers_by_key": {
                (r["asn_text"], r["desc_text"]):
                    {"ip": r["ip"].get(), "password": r["pwd"].get()}
                for r in blk["peers"]
            },
        }

    def _add_bgp_inst_block(self, local_asn, default_peer_asn, slots,
                            prev=None):
        f = ttk.LabelFrame(
            self.bgp_inst_container,
            text=f"BGP {local_asn}", padding=5)
        f.pack(fill="x", padx=2, pady=(4, 0))

        isp_gateway  = _field(f, "ISP Gateway")
        user_network = _field(f, "User Network (advertised)")
        user_mask    = _field(f, "User Network Mask", "255.255.255.0")
        circuit_id   = _field(f, "Circuit ID")

        peers_lf = ttk.LabelFrame(f, text="Peers", padding=5)
        peers_lf.pack(fill="x", padx=2, pady=(4, 0))
        if not slots:
            ttk.Label(peers_lf, style="Hint.TLabel",
                      text="  No peer slots defined in this profile.\n"
                           "  Add slots under Profiles → BGP."
                      ).pack(anchor="w", padx=2, pady=(0, 4))
        else:
            ttk.Label(peers_lf, style="Hint.TLabel",
                      text="  One row per peer slot from the site profile.\n"
                           "  Enter the Peer IP and Password for this switch."
                      ).pack(anchor="w", padx=2, pady=(0, 4))
        ph = ttk.Frame(peers_lf); ph.pack(fill="x")
        ph.columnconfigure(0, weight=1, uniform="swpeers")  # ASN
        ph.columnconfigure(1, weight=2, uniform="swpeers")  # Description
        ph.columnconfigure(2, weight=2, uniform="swpeers")  # Peer IP
        ph.columnconfigure(3, weight=2, uniform="swpeers")  # Password
        ttk.Label(ph, text="Remote ASN", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(ph, text="Description", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(ph, text="Peer IP", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Label(ph, text="Password", anchor="w").grid(
            row=0, column=3, sticky="ew", padx=1)
        peer_frame = ttk.Frame(peers_lf); peer_frame.pack(fill="x")

        block = {
            "frame":        f,
            "local_asn":    local_asn,
            "default_peer_asn": default_peer_asn,
            "isp_gateway":  isp_gateway,
            "user_network": user_network,
            "user_mask":    user_mask,
            "circuit_id":   circuit_id,
            "peer_frame":   peer_frame,
            "peers":        [],
        }

        prev_peers = (prev or {}).get("peers_by_key", {})
        for slot in slots:
            asn_text  = str(slot.get("peer_asn") or default_peer_asn or "").strip()
            desc_text = (slot.get("description") or "").strip()
            self._add_sw_bgp_peer(block, asn_text, desc_text,
                                  prev_peers.get((asn_text, desc_text)))

        if prev:
            isp_gateway.insert(0, prev.get("isp_gateway", ""))
            user_network.insert(0, prev.get("user_network", ""))
            user_mask.delete(0, "end")
            user_mask.insert(0, prev.get("user_mask", "") or "255.255.255.0")
            circuit_id.insert(0, prev.get("circuit_id", ""))

        self.bgp_inst_blocks.append(block)

    def _add_sw_bgp_peer(self, block, asn_text, desc_text, prev=None):
        row = ttk.Frame(block["peer_frame"]); row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=1, uniform="swpeers")
        row.columnconfigure(1, weight=2, uniform="swpeers")
        row.columnconfigure(2, weight=2, uniform="swpeers")
        row.columnconfigure(3, weight=2, uniform="swpeers")
        ttk.Label(row, text=asn_text or "(unset)", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(row, text=desc_text or "", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ip_e  = ttk.Entry(row); ip_e.grid( row=0, column=2, sticky="ew", padx=1)
        pwd_e = ttk.Entry(row); pwd_e.grid(row=0, column=3, sticky="ew", padx=1)
        _attach_context_menu(ip_e); _attach_context_menu(pwd_e)
        if prev:
            ip_e.insert(0, prev.get("ip", ""))
            pwd_e.insert(0, prev.get("password", ""))
        block["peers"].append({
            "frame":     row,
            "asn_text":  asn_text,
            "desc_text": desc_text,
            "ip":        ip_e,
            "pwd":       pwd_e,
        })

    def _sw_dict(self):
        # ttk.Entry.get() works whether or not the widget is disabled
        sw = {
            "hostname":        self.hostname.get().strip(),
            "local_username":  self.username.get().strip(),
            "enable_secret":   self.secret.get().strip(),
            "admin_password":  self.password.get().strip(),
            "domain_name":     self.domain.get().strip(),
            "mgmt_ip":         self.mgmt_ip.get().strip(),
            "mgmt_mask":       self.mgmt_mask.get().strip(),
            "default_gateway": self.gateway.get().strip(),
            "oob_ip":          self.oob_ip.get().strip(),
            "oob_mask":        self.oob_mask.get().strip(),
            "work_order":      self.work_order.get().strip(),
        }
        # L3 fields - only meaningful when the selected profile is L3,
        # but always populated so the renderer can read them safely
        sw["loopback0_ip"]   = self.lb_ip.get().strip()
        sw["loopback0_mask"] = self.lb_mask.get().strip() or "255.255.255.255"
        sw["loopback0_desc"] = self.lb_desc.get().strip()
        sw["routed_mgmt_ip"]   = self.rm_ip.get().strip()
        sw["routed_mgmt_mask"] = self.rm_mask.get().strip()
        sw["mgmt_svi_ip"]      = self.msvi_ip.get().strip()
        sw["mgmt_svi_mask"]    = self.msvi_mask.get().strip()
        sw["router_id"]      = self.router_id.get().strip()
        sw["routed_iface_ips"] = {
            r["iface_name"]: {"ip": r["ip"].get().strip(),
                              "mask": r["mask"].get().strip()}
            for r in self.l3_ip_rows
        }
        sw["svi_ips"] = {
            r["vlan"]: {"ip": r["ip"].get().strip(),
                        "mask": r["mask"].get().strip()}
            for r in self.svi_ip_rows
        }
        sw["static_routes"] = [
            {"prefix":      r["prefix"].get().strip(),
             "mask":        r["mask"].get().strip(),
             "next_hop":    r["nh"].get().strip(),
             "description": r["desc"].get().strip()}
            for r in self.l3_static_rows
            if r["prefix"].get().strip()
        ]
        sw["bgp_instances"] = [
            {
                "local_asn":    blk["local_asn"],
                "isp_gateway":  blk["isp_gateway"].get().strip(),
                "user_network": blk["user_network"].get().strip(),
                "user_mask":    blk["user_mask"].get().strip(),
                "circuit_id":   blk["circuit_id"].get().strip(),
                "peer_fills": [
                    {"peer_asn":    r["asn_text"],
                     "description": r["desc_text"],
                     "peer_ip":     r["ip"].get().strip(),
                     "password":    r["pwd"].get().strip()}
                    for r in blk["peers"]
                ],
            }
            for blk in self.bgp_inst_blocks
        ]
        return sw

    def _get_pa_list(self):
        """Collect port assignments from step-2 rows (skip empty roles)."""
        pas = []
        for r in self.pa_rows:
            iface = r["iface"].get().strip()
            role  = r["role"].get()
            if iface and role and role != "unassigned":
                pas.append({"interfaces": iface, "role": role,
                            "description": r["desc"].get().strip()})
        return pas

    def _generate(self):
        mn = self.model_cb.get()
        pn = self.profile_cb.get()
        sw = self._sw_dict()
        if not sw["hostname"]:
            _dialog("Missing", "Hostname is required.", "warning")
            return

        # build a profile copy with the wizard's port assignments
        profile = dict(self.app.profiles[pn])
        profile["port_assignments"] = self._get_pa_list()

        try:
            self._sections = render_config_sections(
                self.app.models[mn], profile,
                self.app.roles, self.app.resolved_base(profile), sw)
            cfg = "\n\n".join(
                s for s in self._sections.values() if s) + "\n"
        except Exception as exc:
            _dialog("Render Error", str(exc), "error")
            return

        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", cfg)
        self.preview.configure(state="disabled")
        for name, btn in self._qc_buttons.items():
            state = "normal" if self._sections.get(name, "").strip() else "disabled"
            btn.configure(state=state)
        self.app._push_recent("profiles", pn)

    def _save(self):
        txt = self.preview.get("1.0", "end").strip()
        if not txt:
            _dialog("Empty", "Generate a config first.")
            return
        hostname = self.hostname.get().strip() or "switch_config"
        pn = self.profile_cb.get()
        base_for_template = self.app.resolved_base(self.app.profiles.get(pn, {}))
        template = base_for_template.get(
            "filename_template",
            "{{ hostname }}_{{ model }}_{{ profile }}")
        initial = _apply_filename_template(
            template,
            hostname=hostname,
            model=self.model_cb.get(),
            profile=self.profile_cb.get(),
            work_order=self.work_order.get().strip(),
        )
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile=initial,
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            _dialog("Saved", f"Saved to:\n{path}")
            self.app._push_recent("configs", path)

    def _copy(self):
        txt = self.preview.get("1.0", "end").strip()
        if not txt:
            _dialog("Empty", "Generate a config first.")
            return
        self.clipboard_clear()
        self.clipboard_append(txt)
        _dialog("Copied", "Config copied to clipboard.")

    def _copy_section(self, name):
        text = self._sections.get(name, "").strip()
        if not text:
            _dialog("Empty", f"The '{name}' section is empty.", "warning")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        _dialog("Copied", f"'{name}' copied to clipboard.")


# ===================================================================
#  TAB 2 - SWITCH MODELS
# ===================================================================
class ModelsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.pg_rows = []
        self._build()

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Switch Models",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",        command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Select All", command=self.lb.select_all).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete",     command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: edit --
        right = ScrollFrame(paned); paned.add(right, weight=1)
        form = right.inner
        _section(form, "Model Details")
        self.name_e      = _field(form, "Model Name")
        self.provision_e = _field(form, "Provision Type",
                                  default="")
        ttk.Label(form, text="  e.g.  c9300-24s  or  c9200-24p",
                  style="Hint.TLabel").pack(anchor="w", padx=28)
        self.stack_e = _field(form, "Stack Members", default="1")
        ttk.Label(form,
                  text="  Number of switches in the stack (1 = standalone)."
                       "  Port groups are replicated per member.",
                  style="Hint.TLabel").pack(anchor="w", padx=28)

        # port groups
        self.pg_lf = ttk.LabelFrame(form, text="Port Groups", padding=5)
        self.pg_lf.pack(fill="x", padx=5, pady=5)
        hdr = ttk.Frame(self.pg_lf); hdr.pack(fill="x")
        for txt, w in [("Prefix", 24), ("Start", 6), ("End", 6)]:
            ttk.Label(hdr, text=txt, width=w).pack(side="left", padx=1)
        ttk.Button(hdr, text="+ Add Port Group",
                   command=self._add_pg).pack(side="right")
        self.pg_frame = ttk.Frame(self.pg_lf); self.pg_frame.pack(fill="x")

        ttk.Button(form, text="Save Model",
                   command=self._save).pack(padx=5, pady=10, anchor="w")
        self._refresh()

    # -- helpers --
    def _refresh(self):
        self.lb.populate(list(self.app.models.keys()))

    def _clear_pg(self):
        for r in self.pg_rows:
            r["frame"].destroy()
        self.pg_rows.clear()

    def _add_pg(self, data=None):
        row = ttk.Frame(self.pg_frame); row.pack(fill="x", pady=1)
        prefix = ttk.Entry(row, width=24); prefix.pack(side="left", padx=1)
        start  = ttk.Entry(row, width=6);  start.pack(side="left", padx=1)
        end    = ttk.Entry(row, width=6);  end.pack(side="left", padx=1)
        _attach_context_menu(prefix)
        _attach_context_menu(start)
        _attach_context_menu(end)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_pg(row)).pack(side="left", padx=2)
        if data:
            prefix.insert(0, data.get("prefix", ""))
            start.insert(0,  str(data.get("start", "")))
            end.insert(0,    str(data.get("end", "")))
        self.pg_rows.append({"frame": row, "prefix": prefix,
                             "start": start, "end": end})

    def _del_pg(self, frame):
        self.pg_rows = [r for r in self.pg_rows if r["frame"] is not frame]
        frame.destroy()

    # -- actions --
    def _on_select(self, name=None):
        if not name:
            return
        m = self.app.models.get(name, {})
        self.name_e.delete(0, "end");      self.name_e.insert(0, name)
        self.provision_e.delete(0, "end"); self.provision_e.insert(
            0, m.get("provision", ""))
        self.stack_e.delete(0, "end");     self.stack_e.insert(
            0, str(m.get("stack_members", 1)))
        self._clear_pg()
        for pg in m.get("port_groups", []):
            self._add_pg(pg)

    def _new(self):
        self.lb.clear_selection()
        self.name_e.delete(0, "end")
        self.provision_e.delete(0, "end")
        self.stack_e.delete(0, "end"); self.stack_e.insert(0, "1")
        self._clear_pg()

    def _duplicate(self):
        name = self.lb.get_selected()
        if not name:
            _dialog("No Selection", "Select a model to duplicate.")
            return
        data = json.loads(json.dumps(self.app.models.get(name, {})))
        new_name = _copy_name(name, self.app.models)
        self.app.models[new_name] = data
        save_json("models.json", self.app.models)
        self._refresh()
        self.app.gen_tab.refresh_combos()
        self.lb.select(new_name)

    def _delete(self):
        names = self.lb.get_checked()
        if not names:
            sel = self.lb.get_selected()
            if not sel:
                return
            names = [sel]
        if len(names) == 1:
            msg = f"Delete model '{names[0]}'?"
        else:
            msg = f"Delete {len(names)} models?\n\n  " + "\n  ".join(names)
        if _ask("Delete", msg):
            for name in names:
                self.app.models.pop(name, None)
            save_json("models.json", self.app.models)
            self._refresh(); self._new()
            self.app.gen_tab.refresh_combos()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            _dialog("Missing", "Enter a model name.", "warning"); return
        pgs = []
        for r in self.pg_rows:
            try:
                s, e = int(r["start"].get()), int(r["end"].get())
            except ValueError:
                _dialog("Invalid", "Start / End must be numbers.", "warning"); return
            pgs.append({"prefix": r["prefix"].get().strip(),
                        "start": s, "end": e})
        old = self.lb.get_selected()
        if old and old != name and old in self.app.models:
            del self.app.models[old]
        try:
            stack = max(1, int(self.stack_e.get().strip()))
        except ValueError:
            stack = 1
        self.app.models[name] = {"provision": self.provision_e.get().strip(),
                                  "stack_members": stack,
                                  "port_groups": pgs}
        save_json("models.json", self.app.models)
        self._refresh(); self.app.gen_tab.refresh_combos()
        _dialog("Saved", f"Model '{name}' saved.")


# ===================================================================
#  TAB 3 - INTERFACE ROLES
# ===================================================================
class RolesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Interface Roles",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",        command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Select All", command=self.lb.select_all).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete",     command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: edit --
        right = ScrollFrame(paned); paned.add(right, weight=1)
        form = right.inner
        _section(form, "Role Details")
        self.name_e = _field(form, "Role Name")

        self.requires_ip = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="Requires per-switch IP (L3 interface)",
            variable=self.requires_ip
            ).pack(anchor="w", padx=5, pady=(4, 0))
        ttk.Label(form, style="Hint.TLabel",
                  text="  Tick for routed interfaces (Loopback, routed uplinks, etc.).\n"
                       "  Generate Config will then prompt for IP/Mask per switch and\n"
                       "  inject {{ ip }} and {{ mask }} into the role template."
                  ).pack(anchor="w", padx=5, pady=(0, 4))

        _section(form, "IOS Commands")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Enter the IOS commands for this interface role.\n"
                       "  Use {{ variable }} for dynamic values defined in\n"
                       "  the Site Profile.  {{ description }} is always\n"
                       "  available (set per port assignment).\n"
                       "  When 'Requires per-switch IP' is on, {{ ip }} and\n"
                       "  {{ mask }} are also available."
                  ).pack(anchor="w", padx=5, pady=(4, 2))
        self.cmds = tk.Text(form, height=14, font=("Consolas", 10),
                            bg=C["bg_input"], fg=C["green"],
                            insertbackground=C["fg"],
                            selectbackground=C["sel_bg"],
                            relief="flat", bd=2, wrap="word")
        self.cmds.pack(fill="both", expand=True, padx=5, pady=4)
        _attach_context_menu(self.cmds)

        ttk.Button(form, text="Save Role",
                   command=self._save).pack(padx=5, pady=10, anchor="w")
        self._refresh()

    def _refresh(self):
        self.lb.populate(list(self.app.roles.keys()))

    def _on_select(self, name=None):
        if not name:
            return
        role = self.app.roles.get(name, {})
        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.cmds.delete("1.0", "end")
        self.cmds.insert("1.0", role.get("commands", ""))
        self.requires_ip.set(bool(role.get("requires_ip", False)))

    def _new(self):
        self.lb.clear_selection()
        self.name_e.delete(0, "end")
        self.cmds.delete("1.0", "end")
        self.requires_ip.set(False)

    def _duplicate(self):
        name = self.lb.get_selected()
        if not name:
            _dialog("No Selection", "Select a role to duplicate.")
            return
        data = json.loads(json.dumps(self.app.roles.get(name, {})))
        new_name = _copy_name(name, self.app.roles)
        self.app.roles[new_name] = data
        save_json("roles.json", self.app.roles)
        self._refresh()
        self.lb.select(new_name)

    def _delete(self):
        names = self.lb.get_checked()
        if not names:
            sel = self.lb.get_selected()
            if not sel:
                return
            names = [sel]
        if len(names) == 1:
            msg = f"Delete role '{names[0]}'?"
        else:
            msg = f"Delete {len(names)} roles?\n\n  " + "\n  ".join(names)
        if _ask("Delete", msg):
            for name in names:
                self.app.roles.pop(name, None)
            save_json("roles.json", self.app.roles)
            self._refresh(); self._new()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            _dialog("Missing", "Enter a role name.", "warning"); return
        old = self.lb.get_selected()
        if old and old != name and old in self.app.roles:
            del self.app.roles[old]
        data = {"commands": self.cmds.get("1.0", "end").strip()}
        if self.requires_ip.get():
            data["requires_ip"] = True
        self.app.roles[name] = data
        save_json("roles.json", self.app.roles)
        self._refresh()
        _dialog("Saved", f"Role '{name}' saved.")


# ===================================================================
#  TAB 4 - SITE PROFILES
# ===================================================================
class ProfilesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.var_rows = []
        self.pa_rows  = []
        self.svi_rows = []
        self.ospf_net_rows = []
        self.acl_blocks = []   # list of dicts: one per ACL editor block
        self.bgp_blocks = []   # list of dicts: one per BGP instance block
        self._build()

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Site Profiles",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",        command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Select All", command=self.lb.select_all).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete",     command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: edit --
        # Wrapper holds the scrolling form plus a sticky footer with the
        # Save Profile button, so Save stays visible even as the L3 body
        # grows and pushes content off-screen.
        right_wrap = ttk.Frame(paned); paned.add(right_wrap, weight=1)
        footer = ttk.Frame(right_wrap)
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer, orient="horizontal").pack(fill="x")
        ttk.Button(footer, text="Save Profile",
                   command=self._save).pack(padx=5, pady=8, anchor="w")
        right = ScrollFrame(right_wrap); right.pack(fill="both", expand=True)
        form = right.inner

        _section(form, "Profile Details")
        self.name_e = _field(form, "Profile Name")
        self.domain_e = _field(form, "Domain Name")
        self.mgmt_vlan_e = _field(form, "Management VLAN ID")

        # Base Settings selector - which base set this profile uses.
        bs_row = ttk.Frame(form); bs_row.pack(fill="x", padx=5, pady=(2, 4))
        ttk.Label(bs_row, text="Base Settings:").pack(side="left")
        self.base_set_cb = ttk.Combobox(bs_row, width=30, state="readonly",
                                        values=self.app.base_set_names())
        self.base_set_cb.bind("<MouseWheel>", lambda _e: "break")
        self.base_set_cb.pack(side="left", padx=(4, 0))
        ttk.Label(form, style="Hint.TLabel",
                  text="  Leave blank to use the default base set.\n"
                       "  Edit base sets under the Base Settings tab."
                  ).pack(anchor="w", padx=5, pady=(0, 4))

        # -- VLAN definitions (raw IOS) --
        _section(form, "VLAN Definitions")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Paste your VLAN IOS commands here (vlan X / "
                       "name Y / private-vlan / exit)."
                  ).pack(anchor="w", padx=5, pady=(4, 0))
        self.vlans_text = tk.Text(form, height=10, font=("Consolas", 9),
                                  bg=C["bg_input"], fg=C["fg"],
                                  insertbackground=C["fg"],
                                  selectbackground=C["sel_bg"],
                                  relief="flat", bd=2, wrap="word")
        self.vlans_text.pack(fill="x", padx=5, pady=4)
        _attach_context_menu(self.vlans_text)

        # -- Credential defaults --
        _section(form, "Credential Defaults")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Optional defaults pre-filled into Step 3 of\n"
                       "  Generate Config when this profile is selected.\n"
                       "  Leave blank to fall back to Base Settings /\n"
                       "  manual entry. Per-switch edits stay local to\n"
                       "  that wizard run and don't change the profile."
                  ).pack(anchor="w", padx=5, pady=(4, 0))

        cred_lf = ttk.LabelFrame(form, text="Credentials", padding=5)
        cred_lf.pack(fill="x", padx=5, pady=5)
        self.cred_user_e   = _field(cred_lf, "Local Username")
        self.cred_pass_e   = _field(cred_lf, "Local User Password")
        self.cred_enable_e = _field(cred_lf, "Enable Secret")

        # -- DNS / NTP services --
        _section(form, "Services (DNS / NTP)")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Site-wide name-server and NTP settings emitted in\n"
                       "  the Global section. Name Servers and NTP Servers\n"
                       "  accept comma-separated lists. Timezone takes a\n"
                       "  name + offset (e.g. EST -5)."
                  ).pack(anchor="w", padx=5, pady=(4, 0))

        svc_lf = ttk.LabelFrame(form, text="DNS / NTP", padding=5)
        svc_lf.pack(fill="x", padx=5, pady=5)

        self.dns_servers_e  = _field(svc_lf, "Name Servers")
        self.ntp_servers_e  = _field(svc_lf, "NTP Servers")
        self.ntp_source_e   = _field(svc_lf, "NTP Source Interface")
        self.clock_tz_e     = _field(svc_lf, "Clock Timezone")
        self.clock_summer_e = _field(svc_lf, "Clock Summer-Time")
        self.ntp_key_id_e   = _field(svc_lf, "NTP Auth Key ID")
        self.ntp_key_e      = _field(svc_lf, "NTP Auth Key (MD5)")
        ttk.Label(svc_lf, style="Hint.TLabel",
                  text="  NTP authentication fields are optional - leave\n"
                       "  blank to render unauthenticated `ntp server` lines."
                  ).pack(anchor="w", padx=2, pady=(2, 0))

        # -- role variables --
        _section(form, "Role Variables")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Key/value pairs available as {{ key }} inside "
                       "interface role commands."
                  ).pack(anchor="w", padx=5, pady=(4, 0))
        self.var_lf = ttk.LabelFrame(form, text="Variables", padding=5)
        self.var_lf.pack(fill="x", padx=5, pady=5)
        vh = ttk.Frame(self.var_lf); vh.pack(fill="x")
        ttk.Label(vh, text="Key", width=18).pack(side="left", padx=1)
        ttk.Label(vh, text="Value", width=18).pack(side="left", padx=1)
        ttk.Button(vh, text="+ Add Variable",
                   command=self._add_var).pack(side="right")
        self.var_frame = ttk.Frame(self.var_lf); self.var_frame.pack(fill="x")

        # -- port assignments --
        _section(form, "Port Assignments")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Map interface ranges to roles.  These override the\n"
                       "  disabled-port defaults generated from the model."
                  ).pack(anchor="w", padx=5, pady=(4, 0))
        self.pa_lf = ttk.LabelFrame(form, text="Assignments", padding=5)
        self.pa_lf.pack(fill="x", padx=5, pady=5)
        ph = ttk.Frame(self.pa_lf); ph.pack(fill="x")
        ttk.Label(ph, text="Interface(s)", width=26).pack(side="left", padx=1)
        ttk.Label(ph, text="Role", width=16).pack(side="left", padx=1)
        ttk.Label(ph, text="Description", width=20).pack(side="left", padx=1)
        ttk.Button(ph, text="+ Add Assignment",
                   command=self._add_pa).pack(side="right")
        self.pa_frame = ttk.Frame(self.pa_lf); self.pa_frame.pack(fill="x")

        # -- Layer 3 --
        _section(form, "Layer 3")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Enable for sites that do L3 (routed uplinks,\n"
                       "  SVIs as gateways, OSPF). Per-switch values like\n"
                       "  Loopback0 IP, routed-interface IPs, and static\n"
                       "  routes are entered later in Generate Config."
                  ).pack(anchor="w", padx=5, pady=(4, 0))

        l3_top = ttk.Frame(form); l3_top.pack(fill="x", padx=5, pady=4)
        self.l3_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(l3_top, text="Enable Layer 3", variable=self.l3_enabled,
                        command=self._on_layer3_toggle
                        ).pack(side="left")

        # Container holds everything that's hidden when layer3 is off
        self.l3_body = ttk.Frame(form)

        # L3 Interface Sections - each can be independently enabled and
        # has its own IP / Mask defaults that pre-fill Step 3 of Generate
        # Config. Typical workflow: set the Mask in the profile, leave
        # IP blank, fill IP per-switch on Step 3.
        ttk.Label(self.l3_body, style="Hint.TLabel",
                  text="  L3 Interface Sections - check each one you\n"
                       "  want to use. Defaults set here pre-fill the\n"
                       "  matching section on Generate Config Step 3."
                  ).pack(anchor="w", padx=5, pady=(2, 0))

        # --- Loopback0 section ---
        self.lb_sec_lf = ttk.LabelFrame(self.l3_body, padding=5)
        self.lb_sec_lf.pack(fill="x", padx=5, pady=(4, 0))
        self.lb_sec_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.lb_sec_lf, text="Loopback0",
                        variable=self.lb_sec_enabled
                        ).pack(anchor="w")
        self.lb_sec_ip_e   = _field(self.lb_sec_lf, "IP (default)")
        self.lb_sec_mask_e = _field(self.lb_sec_lf, "Mask (default)",
                                    "255.255.255.255")
        self.lb_sec_desc_e = _field(self.lb_sec_lf, "Description",
                                    "Switch MGMT / Router-ID")

        # --- Routed Mgmt Interface section ---
        self.rm_sec_lf = ttk.LabelFrame(self.l3_body, padding=5)
        self.rm_sec_lf.pack(fill="x", padx=5, pady=(4, 0))
        self.rm_sec_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.rm_sec_lf, text="Routed Interface",
                        variable=self.rm_sec_enabled
                        ).pack(anchor="w")
        self.rm_sec_if_e   = _field(self.rm_sec_lf, "Interface")
        self.rm_sec_ip_e   = _field(self.rm_sec_lf, "IP (default)")
        self.rm_sec_mask_e = _field(self.rm_sec_lf, "Mask (default)")
        self.rm_sec_desc_e = _field(self.rm_sec_lf, "Description",
                                    "Routed Mgmt Uplink")

        # --- Management VLAN SVI section ---
        self.msvi_sec_lf = ttk.LabelFrame(self.l3_body, padding=5)
        self.msvi_sec_lf.pack(fill="x", padx=5, pady=(4, 4))
        self.msvi_sec_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.msvi_sec_lf, text="Management VLAN",
                        variable=self.msvi_sec_enabled
                        ).pack(anchor="w")
        self.msvi_sec_vlan_e = _field(self.msvi_sec_lf, "VLAN ID")
        self.msvi_sec_ip_e   = _field(self.msvi_sec_lf, "IP (default)")
        self.msvi_sec_mask_e = _field(self.msvi_sec_lf, "Mask (default)")
        self.msvi_sec_desc_e = _field(self.msvi_sec_lf, "Description",
                                      "Switch MGMT")

        # Default routed-interface subnet mask - pre-fills the Mask column
        # of every routed-interface row in Generate Config Step 3.
        rm = ttk.Frame(self.l3_body); rm.pack(fill="x", padx=5, pady=2)
        ttk.Label(rm, text="Default Routed Mask", width=22, anchor="w"
                  ).pack(side="left")
        self.default_routed_mask_e = ttk.Entry(rm)
        self.default_routed_mask_e.pack(side="left", fill="x", expand=True)
        _attach_context_menu(self.default_routed_mask_e)
        ttk.Label(self.l3_body, style="Hint.TLabel",
                  text="  Pre-fills the Mask column for each routed\n"
                       "  interface in Generate Config Step 3."
                  ).pack(anchor="w", padx=5, pady=(0, 4))

        # SVIs (site-wide gateways)
        self.svi_lf = ttk.LabelFrame(self.l3_body, text="SVIs", padding=5)
        self.svi_lf.pack(fill="x", padx=5, pady=4)

        svi_hint = ttk.Frame(self.svi_lf); svi_hint.pack(fill="x", pady=(0, 4))
        ttk.Label(svi_hint, style="Hint.TLabel",
                  text="  Define the VLANs that need an SVI on every\n"
                       "  switch at the site. IP / Mask pre-fill Step 3\n"
                       "  (typically set Mask here, IP per-switch)."
                  ).pack(side="left", anchor="w", padx=2)
        ttk.Button(svi_hint, text="+ Add SVI",
                   command=self._add_svi
                   ).pack(side="right", anchor="ne", padx=(6, 1))

        sh = ttk.Frame(self.svi_lf); sh.pack(fill="x")
        # Grid: 0 vlan | 1 description | 2 ip | 3 mask | 4 helpers | 5 X col.
        sh.columnconfigure(0, weight=1, uniform="svi")
        sh.columnconfigure(1, weight=3, uniform="svi")
        sh.columnconfigure(2, weight=2, uniform="svi")
        sh.columnconfigure(3, weight=2, uniform="svi")
        sh.columnconfigure(4, weight=3, uniform="svi")
        ttk.Label(sh, text="VLAN", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(sh, text="Description", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(sh, text="IP", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Label(sh, text="Mask", anchor="w").grid(
            row=0, column=3, sticky="ew", padx=1)
        ttk.Label(sh, text="Helpers (CSV)", anchor="w").grid(
            row=0, column=4, sticky="ew", padx=1)
        ttk.Frame(sh, width=30).grid(row=0, column=5, padx=(6, 1))
        self.svi_frame = ttk.Frame(self.svi_lf); self.svi_frame.pack(fill="x")

        # OSPF
        self.ospf_lf = ttk.LabelFrame(self.l3_body, text="OSPF", padding=5)
        self.ospf_lf.pack(fill="x", padx=5, pady=4)
        self.ospf_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.ospf_lf, text="Enable OSPF",
                        variable=self.ospf_enabled
                        ).pack(anchor="w")
        self.ospf_pid_e = _field(self.ospf_lf, "Process ID", "1")
        self.ospf_passive_default = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.ospf_lf, text="Passive interface default",
            variable=self.ospf_passive_default
            ).pack(anchor="w", padx=5, pady=(2, 0))
        self.ospf_passive_e = _field(
            self.ospf_lf,
            "Passive Interfaces (CSV)")
        ospf_hint = ttk.Frame(self.ospf_lf)
        ospf_hint.pack(fill="x", padx=5, pady=(0, 4))
        ttk.Label(ospf_hint, style="Hint.TLabel",
                  text="  When 'passive default' is on, listed interfaces "
                       "become exceptions (active).\n"
                       "  When off, only listed interfaces are passive.\n"
                       "  Router-ID is set per switch in Generate Config\n"
                       "  (defaults to the Loopback0 IP)."
                  ).pack(side="left", anchor="w")
        ttk.Button(ospf_hint, text="+ Add Network",
                   command=self._add_ospf_net
                   ).pack(side="right", anchor="ne", padx=(6, 1))

        nh = ttk.Frame(self.ospf_lf); nh.pack(fill="x", pady=(4, 0))
        ttk.Label(nh, text="Network", width=18).pack(side="left", padx=1)
        ttk.Label(nh, text="Wildcard", width=18).pack(side="left", padx=1)
        ttk.Label(nh, text="Area", width=8).pack(side="left", padx=1)
        self.ospf_net_frame = ttk.Frame(self.ospf_lf)
        self.ospf_net_frame.pack(fill="x")

        # BGP - one or more instances, each rendered as its own
        # `router bgp <asn>` block. Same +Add/X pattern as ACLs.
        self.bgp_outer_lf = ttk.LabelFrame(
            self.l3_body, text="BGP", padding=5)
        self.bgp_outer_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.bgp_outer_lf, style="Hint.TLabel",
                  text="  Add one BGP instance per local ASN. Each renders\n"
                       "  as its own `router bgp <asn>` block with its own\n"
                       "  peers and advertised network."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        ttk.Button(self.bgp_outer_lf, text="+ Add BGP",
                   command=lambda: self._add_bgp_block()
                   ).pack(anchor="w", pady=(0, 4))
        self.bgp_container = ttk.Frame(self.bgp_outer_lf)
        self.bgp_container.pack(fill="x")

        # ACLs (site-wide named access-lists)
        self.acl_lf = ttk.LabelFrame(self.l3_body, text="Access Lists", padding=5)
        self.acl_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.acl_lf, style="Hint.TLabel",
                  text="  Named ACLs rendered after the interfaces section.\n"
                       "  Order matters - rules emit in the order shown."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        ttk.Button(self.acl_lf, text="+ Add ACL",
                   command=lambda: self._add_acl_block()
                   ).pack(anchor="w", pady=(0, 4))
        self.acl_container = ttk.Frame(self.acl_lf)
        self.acl_container.pack(fill="x")

        self._refresh()

    # -- list helpers --
    def _refresh(self):
        self.lb.populate(list(self.app.profiles.keys()))

    # -- variable rows --
    def _clear_vars(self):
        for r in self.var_rows:
            r["frame"].destroy()
        self.var_rows.clear()

    def _add_var(self, data=None):
        row = ttk.Frame(self.var_frame); row.pack(fill="x", pady=1)
        k = ttk.Entry(row, width=18); k.pack(side="left", padx=1)
        v = ttk.Entry(row, width=18); v.pack(side="left", padx=1)
        _attach_context_menu(k)
        _attach_context_menu(v)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.var_rows)
                   ).pack(side="left", padx=2)
        if data:
            k.insert(0, data[0]); v.insert(0, data[1])
        self.var_rows.append({"frame": row, "key": k, "val": v})

    # -- port assignment rows --
    def _clear_pa(self):
        for r in self.pa_rows:
            r["frame"].destroy()
        self.pa_rows.clear()

    def _add_pa(self, data=None):
        row = ttk.Frame(self.pa_frame); row.pack(fill="x", pady=1)
        iface = ttk.Entry(row, width=26);   iface.pack(side="left", padx=1)
        _attach_context_menu(iface)
        role  = ttk.Combobox(row, width=14, state="readonly",
                             values=["unassigned"] + list(self.app.roles.keys()))
        role.bind("<MouseWheel>", lambda _e: "break")
        role.pack(side="left", padx=1)
        desc  = ttk.Entry(row, width=20);   desc.pack(side="left", padx=1)
        _attach_context_menu(desc)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.pa_rows)
                   ).pack(side="left", padx=2)
        if data:
            iface.insert(0, data.get("interfaces", ""))
            role.set(data.get("role", "") or "unassigned")
            desc.insert(0, data.get("description", ""))
        self.pa_rows.append({"frame": row, "iface": iface,
                             "role": role, "desc": desc})

    def _del_row(self, frame, lst):
        lst[:] = [r for r in lst if r["frame"] is not frame]
        frame.destroy()

    # -- layer 3 row helpers --
    def _on_layer3_toggle(self):
        if self.l3_enabled.get():
            self.l3_body.pack(fill="x", padx=0, pady=(0, 4))
        else:
            self.l3_body.pack_forget()

    def _clear_svis(self):
        for r in self.svi_rows:
            r["frame"].destroy()
        self.svi_rows.clear()

    def _add_svi(self, data=None):
        row = ttk.Frame(self.svi_frame); row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=1, uniform="svi")
        row.columnconfigure(1, weight=3, uniform="svi")
        row.columnconfigure(2, weight=2, uniform="svi")
        row.columnconfigure(3, weight=2, uniform="svi")
        row.columnconfigure(4, weight=3, uniform="svi")
        vlan = ttk.Entry(row); vlan.grid(row=0, column=0, sticky="ew", padx=1)
        desc = ttk.Entry(row); desc.grid(row=0, column=1, sticky="ew", padx=1)
        ip   = ttk.Entry(row); ip.grid(  row=0, column=2, sticky="ew", padx=1)
        mask = ttk.Entry(row); mask.grid(row=0, column=3, sticky="ew", padx=1)
        hlp  = ttk.Entry(row); hlp.grid( row=0, column=4, sticky="ew", padx=1)
        for w in (vlan, desc, ip, mask, hlp):
            _attach_context_menu(w)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.svi_rows)
                   ).grid(row=0, column=5, padx=(6, 1))
        if data:
            vlan.insert(0, data.get("vlan", ""))
            desc.insert(0, data.get("description", "") or data.get("name", ""))
            ip.insert(0, data.get("ip", "") or "")
            mask.insert(0, data.get("mask", "") or "")
            helpers = data.get("helper_addresses", "")
            if isinstance(helpers, list):
                helpers = ", ".join(str(h) for h in helpers)
            hlp.insert(0, helpers or "")
        self.svi_rows.append({"frame": row, "vlan": vlan, "desc": desc,
                              "ip": ip, "mask": mask, "hlp": hlp})

    def _clear_ospf_nets(self):
        for r in self.ospf_net_rows:
            r["frame"].destroy()
        self.ospf_net_rows.clear()

    def _add_ospf_net(self, data=None):
        row = ttk.Frame(self.ospf_net_frame); row.pack(fill="x", pady=1)
        net  = ttk.Entry(row, width=18);  net.pack(side="left", padx=1)
        wc   = ttk.Entry(row, width=18);  wc.pack(side="left", padx=1)
        area = ttk.Entry(row, width=8);   area.pack(side="left", padx=1)
        for w in (net, wc, area):
            _attach_context_menu(w)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.ospf_net_rows)
                   ).pack(side="left", padx=2)
        if data:
            net.insert(0, data.get("network", ""))
            wc.insert(0, data.get("wildcard", ""))
            area.insert(0, str(data.get("area", "") or ""))
        self.ospf_net_rows.append({"frame": row, "net": net, "wc": wc,
                                   "area": area})

    # -- ACL editor --
    _ACL_ACTIONS = ("permit", "deny", "remark")

    def _clear_acls(self):
        for blk in self.acl_blocks:
            blk["frame"].destroy()
        self.acl_blocks.clear()

    def _add_acl_block(self, data=None):
        blk_frame = ttk.LabelFrame(self.acl_container, padding=5)
        blk_frame.pack(fill="x", pady=(0, 6))

        top = ttk.Frame(blk_frame); top.pack(fill="x")
        ttk.Label(top, text="Name:").pack(side="left")
        name_e = ttk.Entry(top, width=24); name_e.pack(side="left", padx=(4, 10))
        _attach_context_menu(name_e)
        ttk.Label(top, text="Type:").pack(side="left")
        type_cb = ttk.Combobox(top, width=12, state="readonly",
                               values=["extended", "standard"])
        type_cb.bind("<MouseWheel>", lambda _e: "break")
        type_cb.pack(side="left", padx=4)
        type_cb.set("extended")

        rule_rows = []
        ttk.Button(top, text="X", width=3, style="Del.TButton",
                   command=lambda f=blk_frame: self._del_acl_block(f)
                   ).pack(side="right")

        rules_frame = ttk.Frame(blk_frame)
        rules_frame.pack(fill="x", pady=(4, 0))

        btn_row = ttk.Frame(blk_frame); btn_row.pack(fill="x", pady=(4, 0))
        block = {"frame": blk_frame, "name": name_e, "type": type_cb,
                 "rules": rule_rows, "rules_frame": rules_frame}
        ttk.Button(btn_row, text="+ Add Rule",
                   command=lambda b=block: self._add_acl_rule(b)
                   ).pack(side="left")

        self.acl_blocks.append(block)

        if data:
            name_e.insert(0, data.get("name", ""))
            type_cb.set(data.get("type", "extended") or "extended")
            for rule in data.get("rules", []) or []:
                self._add_acl_rule(block, rule)

    def _del_acl_block(self, frame):
        self.acl_blocks[:] = [b for b in self.acl_blocks
                              if b["frame"] is not frame]
        frame.destroy()

    def _add_acl_rule(self, block, data=None):
        row = ttk.Frame(block["rules_frame"]); row.pack(fill="x", pady=1)
        # Grid columns:  0 action | 1 proto | 2 src | 3 src_wc |
        #                4 dst    | 5 dst_wc | 6 log | 7 X
        # Action / proto / log / X stay at their natural width; the four
        # address columns share equal weight so the row fills the rules
        # frame and stays the same length whether the action is permit,
        # deny, or remark - and adapts when the window is narrow.
        for col in (2, 3, 4, 5):
            row.columnconfigure(col, weight=1, uniform="acladdrs")
        action_cb = ttk.Combobox(row, width=8, state="readonly",
                                 values=list(self._ACL_ACTIONS))
        action_cb.bind("<MouseWheel>", lambda _e: "break")
        action_cb.grid(row=0, column=0, sticky="ew", padx=1)
        proto_e = ttk.Entry(row, width=4)
        src_e   = ttk.Entry(row)
        srcwc_e = ttk.Entry(row)
        dst_e   = ttk.Entry(row)
        dstwc_e = ttk.Entry(row)
        proto_e.grid(row=0, column=1, sticky="ew", padx=1)
        src_e.grid(  row=0, column=2, sticky="ew", padx=1)
        srcwc_e.grid(row=0, column=3, sticky="ew", padx=1)
        dst_e.grid(  row=0, column=4, sticky="ew", padx=1)
        dstwc_e.grid(row=0, column=5, sticky="ew", padx=1)
        log_var = tk.BooleanVar(value=False)
        log_cb  = ttk.Checkbutton(row, text="log", variable=log_var)
        log_cb.grid(row=0, column=6, sticky="w", padx=2)
        for w in (proto_e, src_e, srcwc_e, dst_e, dstwc_e):
            _attach_context_menu(w)
        del_btn = ttk.Button(row, text="X", width=3, style="Del.TButton",
                             command=lambda r=row, b=block:
                                 self._del_acl_rule(r, b))
        del_btn.grid(row=0, column=7, sticky="e", padx=2)

        rule = {"frame": row, "action": action_cb, "proto": proto_e,
                "src": src_e, "src_wc": srcwc_e,
                "dst": dst_e, "dst_wc": dstwc_e, "log": log_var}

        # When the action is 'remark', collapse the rule fields into a
        # single text entry that spans columns 1–6 (everything between
        # the action combobox and the delete button). Row width and
        # sash alignment stay identical to permit/deny rows.
        def _refresh_action_layout(*_):
            act = action_cb.get() or "permit"
            if act == "remark":
                for w in (proto_e, src_e, srcwc_e, dst_e, dstwc_e, log_cb):
                    w.grid_remove()
                rmk = rule.get("remark")
                if rmk is None:
                    rmk = ttk.Entry(row)
                    _attach_context_menu(rmk)
                    rule["remark"] = rmk
                rmk.grid(row=0, column=1, columnspan=6,
                         sticky="ew", padx=1)
            else:
                rmk = rule.get("remark")
                if rmk is not None:
                    rmk.grid_remove()
                proto_e.grid()
                src_e.grid()
                srcwc_e.grid()
                dst_e.grid()
                dstwc_e.grid()
                log_cb.grid()

        action_cb.bind("<<ComboboxSelected>>", _refresh_action_layout)

        if data:
            act = data.get("action", "permit") or "permit"
            action_cb.set(act)
            if act == "remark":
                _refresh_action_layout()
                rule["remark"].insert(0, data.get("text", ""))
            else:
                proto_e.insert(0, data.get("protocol", "ip") or "ip")
                src_e.insert(0, data.get("source", ""))
                srcwc_e.insert(0, data.get("source_wildcard", ""))
                dst_e.insert(0, data.get("dest", ""))
                dstwc_e.insert(0, data.get("dest_wildcard", ""))
                log_var.set(bool(data.get("log", False)))
        else:
            action_cb.set("permit")
            proto_e.insert(0, "ip")

        block["rules"].append(rule)

    def _del_acl_rule(self, row, block):
        block["rules"][:] = [r for r in block["rules"] if r["frame"] is not row]
        row.destroy()

    # -- BGP instance blocks --
    def _clear_bgp_blocks(self):
        for blk in self.bgp_blocks:
            blk["frame"].destroy()
        self.bgp_blocks.clear()

    def _add_bgp_block(self, data=None):
        blk_frame = ttk.LabelFrame(self.bgp_container, padding=5)
        blk_frame.pack(fill="x", pady=(0, 6))

        top = ttk.Frame(blk_frame); top.pack(fill="x")
        ttk.Label(top, text="Local ASN:").pack(side="left")
        local_e = ttk.Entry(top, width=10)
        local_e.pack(side="left", padx=(4, 10))
        _attach_context_menu(local_e)
        ttk.Label(top, text="Default Peer ASN:").pack(side="left")
        peer_asn_e = ttk.Entry(top, width=10)
        peer_asn_e.pack(side="left", padx=(4, 10))
        _attach_context_menu(peer_asn_e)
        ttk.Button(top, text="X", width=3, style="Del.TButton",
                   command=lambda f=blk_frame: self._del_bgp_block(f)
                   ).pack(side="right")
        ttk.Label(blk_frame, style="Hint.TLabel",
                  text="  Default Peer ASN pre-fills new peer rows below\n"
                       "  and per-switch peers in Generate Config. Each peer\n"
                       "  carries its own ASN, so peers from different\n"
                       "  upstreams within this instance are fine."
                  ).pack(anchor="w", padx=2, pady=(2, 4))

        slots_lf = ttk.LabelFrame(blk_frame, text="Peer Slots", padding=5)
        slots_lf.pack(fill="x", padx=2, pady=(4, 0))

        hint_row = ttk.Frame(slots_lf); hint_row.pack(fill="x", pady=(0, 4))
        ttk.Label(hint_row, style="Hint.TLabel",
                  text="  Each slot describes one BGP neighbor that will\n"
                       "  exist on every switch built from this profile.\n"
                       "  Peer IP and password are entered per-switch in\n"
                       "  Generate Config."
                  ).pack(side="left", anchor="w", padx=2)

        slot_frame = ttk.Frame(slots_lf)
        block = {"frame": blk_frame, "local_asn": local_e,
                 "peer_asn": peer_asn_e, "slot_frame": slot_frame,
                 "slots": []}
        ttk.Button(hint_row, text="+ Add Slot",
                   command=lambda b=block: self._add_bgp_slot(b)
                   ).pack(side="right", anchor="ne", padx=(6, 1))

        ph = ttk.Frame(slots_lf); ph.pack(fill="x")
        ph.columnconfigure(0, weight=1, uniform="bgpslots")
        ph.columnconfigure(1, weight=3, uniform="bgpslots")
        ttk.Label(ph, text="Remote ASN", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(ph, text="Description", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Frame(ph, width=30).grid(row=0, column=2, padx=(6, 1))

        slot_frame.pack(fill="x")

        self.bgp_blocks.append(block)

        if data:
            local_e.insert(0, str(data.get("local_asn", "") or ""))
            peer_asn_e.insert(0, str(data.get("peer_asn", "") or ""))
            # accept the older "peers" key from existing profiles by
            # treating each peer as a slot (drop IP/password fields).
            slots = data.get("slots")
            if slots is None:
                slots = [{"peer_asn": p.get("peer_asn"),
                          "description": p.get("description")}
                         for p in (data.get("peers") or [])]
            for slot in slots:
                self._add_bgp_slot(block, slot)
        else:
            local_e.insert(0, "65000")
            peer_asn_e.insert(0, "65001")

    def _del_bgp_block(self, frame):
        self.bgp_blocks[:] = [b for b in self.bgp_blocks
                              if b["frame"] is not frame]
        frame.destroy()

    def _add_bgp_slot(self, block, data=None):
        row = ttk.Frame(block["slot_frame"]); row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=1, uniform="bgpslots")
        row.columnconfigure(1, weight=3, uniform="bgpslots")
        asn_e  = ttk.Entry(row); asn_e.grid( row=0, column=0, sticky="ew", padx=1)
        desc_e = ttk.Entry(row); desc_e.grid(row=0, column=1, sticky="ew", padx=1)
        for w in (asn_e, desc_e):
            _attach_context_menu(w)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda r=row, b=block:
                       self._del_bgp_slot(r, b)
                   ).grid(row=0, column=2, padx=(6, 1))
        if data:
            asn_e.insert(0, str(data.get("peer_asn", "") or ""))
            desc_e.insert(0, data.get("description", ""))
        else:
            asn_e.insert(0, block["peer_asn"].get().strip())
        block["slots"].append({"frame": row, "asn": asn_e, "desc": desc_e})

    def _del_bgp_slot(self, row, block):
        block["slots"][:] = [r for r in block["slots"]
                             if r["frame"] is not row]
        row.destroy()

    def _collect_bgp_instances(self):
        out = []
        for blk in self.bgp_blocks:
            local_asn = blk["local_asn"].get().strip()
            if not local_asn:
                continue
            slots = []
            for r in blk["slots"]:
                slots.append({
                    "peer_asn":    r["asn"].get().strip(),
                    "description": r["desc"].get().strip(),
                })
            out.append({
                "local_asn": local_asn,
                "peer_asn":  blk["peer_asn"].get().strip(),
                "slots":     slots,
            })
        return out

    def _collect_acls(self):
        out = []
        for blk in self.acl_blocks:
            name = blk["name"].get().strip()
            if not name:
                continue
            acl = {"name": name,
                   "type": blk["type"].get() or "extended",
                   "rules": []}
            for r in blk["rules"]:
                act = r["action"].get() or "permit"
                if act == "remark":
                    text = r.get("remark")
                    text = text.get().strip() if text is not None else ""
                    if text:
                        acl["rules"].append({"action": "remark", "text": text})
                else:
                    acl["rules"].append({
                        "action": act,
                        "protocol": r["proto"].get().strip() or "ip",
                        "source": r["src"].get().strip(),
                        "source_wildcard": r["src_wc"].get().strip(),
                        "dest": r["dst"].get().strip(),
                        "dest_wildcard": r["dst_wc"].get().strip(),
                        "log": bool(r["log"].get()),
                    })
            out.append(acl)
        return out

    # -- actions --
    def _on_select(self, name=None):
        if not name:
            return
        p = self.app.profiles.get(name, {})

        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.domain_e.delete(0, "end")
        self.domain_e.insert(0, p.get("domain_name", ""))
        self.mgmt_vlan_e.delete(0, "end")
        self.mgmt_vlan_e.insert(0, p.get("mgmt_vlan", ""))

        self.base_set_cb["values"] = self.app.base_set_names()
        self.base_set_cb.set(p.get("base_set", "") or "")

        creds = p.get("credentials", {}) or {}
        self.cred_user_e.delete(0, "end")
        self.cred_user_e.insert(0, creds.get("local_username", "") or "")
        self.cred_pass_e.delete(0, "end")
        self.cred_pass_e.insert(0, creds.get("admin_password", "") or "")
        self.cred_enable_e.delete(0, "end")
        self.cred_enable_e.insert(0, creds.get("enable_secret", "") or "")

        svc = p.get("services", {}) or {}
        dns_list = svc.get("dns_servers") or []
        if isinstance(dns_list, list):
            dns_list = ", ".join(str(x) for x in dns_list)
        self.dns_servers_e.delete(0, "end")
        self.dns_servers_e.insert(0, dns_list)

        ntp = svc.get("ntp") or {}
        ntp_list = ntp.get("servers") or []
        if isinstance(ntp_list, list):
            ntp_list = ", ".join(str(x) for x in ntp_list)
        self.ntp_servers_e.delete(0, "end")
        self.ntp_servers_e.insert(0, ntp_list)
        self.ntp_source_e.delete(0, "end")
        self.ntp_source_e.insert(0, ntp.get("source_interface", "") or "")
        self.clock_tz_e.delete(0, "end")
        self.clock_tz_e.insert(0, svc.get("clock_timezone", "") or "")
        self.clock_summer_e.delete(0, "end")
        self.clock_summer_e.insert(0, svc.get("clock_summer_time", "") or "")
        self.ntp_key_id_e.delete(0, "end")
        self.ntp_key_id_e.insert(0, ntp.get("auth_key_id", "") or "")
        self.ntp_key_e.delete(0, "end")
        self.ntp_key_e.insert(0, ntp.get("auth_key", "") or "")

        self.vlans_text.delete("1.0", "end")
        self.vlans_text.insert("1.0", p.get("vlan_definitions", ""))

        self._clear_vars()
        for k, v in p.get("role_variables", {}).items():
            self._add_var((k, v))

        self._clear_pa()
        for pa in p.get("port_assignments", []):
            self._add_pa(pa)

        # Layer 3
        self.l3_enabled.set(bool(p.get("layer3", False)))
        sections = _normalize_l3_sections(p)
        lb = sections.get("loopback", {})
        self.lb_sec_enabled.set(bool(lb.get("enabled")))
        for w, v in ((self.lb_sec_ip_e,   lb.get("ip", "")),
                     (self.lb_sec_mask_e, lb.get("mask", "255.255.255.255")),
                     (self.lb_sec_desc_e, lb.get("description",
                                                  "Switch MGMT / Router-ID"))):
            w.delete(0, "end"); w.insert(0, v or "")
        rm = sections.get("routed_mgmt", {})
        self.rm_sec_enabled.set(bool(rm.get("enabled")))
        for w, v in ((self.rm_sec_if_e,   rm.get("interface", "")),
                     (self.rm_sec_ip_e,   rm.get("ip", "")),
                     (self.rm_sec_mask_e, rm.get("mask", "")),
                     (self.rm_sec_desc_e, rm.get("description",
                                                  "Routed Mgmt Uplink"))):
            w.delete(0, "end"); w.insert(0, v or "")
        msvi = sections.get("mgmt_svi", {})
        self.msvi_sec_enabled.set(bool(msvi.get("enabled")))
        for w, v in ((self.msvi_sec_vlan_e, msvi.get("vlan", "")),
                     (self.msvi_sec_ip_e,   msvi.get("ip", "")),
                     (self.msvi_sec_mask_e, msvi.get("mask", "")),
                     (self.msvi_sec_desc_e, msvi.get("description",
                                                     "Switch MGMT"))):
            w.delete(0, "end"); w.insert(0, v or "")
        self.default_routed_mask_e.delete(0, "end")
        self.default_routed_mask_e.insert(
            0, p.get("default_routed_mask", "") or "")

        self._clear_svis()
        for svi in p.get("svis", []) or []:
            self._add_svi(svi)

        ospf = p.get("ospf", {}) or {}
        self.ospf_enabled.set(bool(ospf.get("enabled", False)))
        self.ospf_pid_e.delete(0, "end")
        self.ospf_pid_e.insert(0, str(ospf.get("process_id", "1") or "1"))
        self.ospf_passive_default.set(bool(ospf.get("passive_default", False)))
        passive = ospf.get("passive_interfaces", []) or []
        if isinstance(passive, list):
            passive = ", ".join(str(x) for x in passive)
        self.ospf_passive_e.delete(0, "end")
        self.ospf_passive_e.insert(0, passive)
        self._clear_ospf_nets()
        for n in ospf.get("networks", []) or []:
            self._add_ospf_net(n)

        bgp = p.get("bgp", {}) or {}
        self._clear_bgp_blocks()
        for inst in bgp.get("instances", []) or []:
            self._add_bgp_block(inst)

        self._clear_acls()
        for acl in p.get("acls", []) or []:
            self._add_acl_block(acl)

        self._on_layer3_toggle()

    def refresh_base_sets(self):
        """Update the Base Settings dropdown values after the BaseTab
        adds/removes/renames a set."""
        cur = self.base_set_cb.get()
        names = self.app.base_set_names()
        self.base_set_cb["values"] = names
        if cur and cur not in names:
            self.base_set_cb.set("")

    def _new(self):
        self.lb.clear_selection()
        self.name_e.delete(0, "end")
        self.domain_e.delete(0, "end")
        self.mgmt_vlan_e.delete(0, "end")
        self.base_set_cb["values"] = self.app.base_set_names()
        self.base_set_cb.set("")
        for w in (self.cred_user_e, self.cred_pass_e, self.cred_enable_e,
                  self.dns_servers_e, self.ntp_servers_e,
                  self.ntp_source_e, self.clock_tz_e,
                  self.clock_summer_e, self.ntp_key_id_e, self.ntp_key_e):
            w.delete(0, "end")
        self.vlans_text.delete("1.0", "end")
        self._clear_vars(); self._clear_pa()
        # Layer 3 defaults for a new profile
        self.l3_enabled.set(False)
        self.lb_sec_enabled.set(False)
        self.rm_sec_enabled.set(False)
        self.msvi_sec_enabled.set(False)
        for w in (self.lb_sec_ip_e, self.lb_sec_mask_e, self.lb_sec_desc_e,
                  self.rm_sec_if_e, self.rm_sec_ip_e, self.rm_sec_mask_e,
                  self.rm_sec_desc_e,
                  self.msvi_sec_vlan_e, self.msvi_sec_ip_e,
                  self.msvi_sec_mask_e, self.msvi_sec_desc_e):
            w.delete(0, "end")
        self.lb_sec_mask_e.insert(0, "255.255.255.255")
        self.lb_sec_desc_e.insert(0, "Switch MGMT / Router-ID")
        self.rm_sec_desc_e.insert(0, "Routed Mgmt Uplink")
        self.msvi_sec_desc_e.insert(0, "Switch MGMT")
        self.default_routed_mask_e.delete(0, "end")
        self._clear_svis()
        self.ospf_enabled.set(False)
        self.ospf_pid_e.delete(0, "end"); self.ospf_pid_e.insert(0, "1")
        self.ospf_passive_default.set(False)
        self.ospf_passive_e.delete(0, "end")
        self._clear_ospf_nets()
        self._clear_bgp_blocks()
        self._clear_acls()
        self._on_layer3_toggle()

    def _duplicate(self):
        name = self.lb.get_selected()
        if not name:
            _dialog("No Selection", "Select a profile to duplicate.")
            return
        data = json.loads(json.dumps(self.app.profiles.get(name, {})))
        new_name = _copy_name(name, self.app.profiles)
        self.app.profiles[new_name] = data
        save_json("profiles.json", self.app.profiles)
        self._refresh()
        self.app.gen_tab.refresh_combos()
        self.lb.select(new_name)

    def _delete(self):
        names = self.lb.get_checked()
        if not names:
            sel = self.lb.get_selected()
            if not sel:
                return
            names = [sel]
        if len(names) == 1:
            msg = f"Delete profile '{names[0]}'?"
        else:
            msg = f"Delete {len(names)} profiles?\n\n  " + "\n  ".join(names)
        if _ask("Delete", msg):
            for name in names:
                self.app.profiles.pop(name, None)
            save_json("profiles.json", self.app.profiles)
            self._refresh(); self._new()
            self.app.gen_tab.refresh_combos()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            _dialog("Missing", "Enter a profile name.", "warning"); return

        role_vars = {}
        for r in self.var_rows:
            k = r["key"].get().strip()
            if k:
                role_vars[k] = r["val"].get().strip()

        pas = []
        for r in self.pa_rows:
            iface = r["iface"].get().strip()
            if iface:
                pas.append({"interfaces": iface,
                            "role": r["role"].get(),
                            "description": r["desc"].get().strip()})

        old = self.lb.get_selected()
        if old and old != name and old in self.app.profiles:
            del self.app.profiles[old]

        credentials = {}
        if self.cred_user_e.get().strip():
            credentials["local_username"] = self.cred_user_e.get().strip()
        if self.cred_pass_e.get().strip():
            credentials["admin_password"] = self.cred_pass_e.get().strip()
        if self.cred_enable_e.get().strip():
            credentials["enable_secret"] = self.cred_enable_e.get().strip()

        dns_servers = [s.strip() for s in self.dns_servers_e.get().split(",")
                       if s.strip()]
        ntp_servers = [s.strip() for s in self.ntp_servers_e.get().split(",")
                       if s.strip()]
        services = {}
        if dns_servers:
            services["dns_servers"] = dns_servers
        ntp_block = {}
        if ntp_servers:
            ntp_block["servers"] = ntp_servers
        if self.ntp_source_e.get().strip():
            ntp_block["source_interface"] = self.ntp_source_e.get().strip()
        if self.ntp_key_id_e.get().strip():
            ntp_block["auth_key_id"] = self.ntp_key_id_e.get().strip()
        if self.ntp_key_e.get().strip():
            ntp_block["auth_key"] = self.ntp_key_e.get().strip()
        if ntp_block:
            services["ntp"] = ntp_block
        if self.clock_tz_e.get().strip():
            services["clock_timezone"] = self.clock_tz_e.get().strip()
        if self.clock_summer_e.get().strip():
            services["clock_summer_time"] = self.clock_summer_e.get().strip()

        data = {
            "domain_name":      self.domain_e.get().strip(),
            "mgmt_vlan":        self.mgmt_vlan_e.get().strip(),
            "base_set":         self.base_set_cb.get().strip(),
            "vlan_definitions": self.vlans_text.get("1.0", "end").strip(),
            "role_variables":   role_vars,
            "port_assignments": pas,
        }
        if services:
            data["services"] = services
        if credentials:
            data["credentials"] = credentials

        # Layer 3 (only persisted when enabled, to keep old profiles clean)
        if self.l3_enabled.get():
            data["layer3"] = True
            data["l3_sections"] = {
                "loopback": {
                    "enabled":     bool(self.lb_sec_enabled.get()),
                    "ip":          self.lb_sec_ip_e.get().strip(),
                    "mask":        (self.lb_sec_mask_e.get().strip()
                                    or "255.255.255.255"),
                    "description": (self.lb_sec_desc_e.get().strip()
                                    or "Switch MGMT / Router-ID"),
                },
                "routed_mgmt": {
                    "enabled":     bool(self.rm_sec_enabled.get()),
                    "interface":   self.rm_sec_if_e.get().strip(),
                    "ip":          self.rm_sec_ip_e.get().strip(),
                    "mask":        self.rm_sec_mask_e.get().strip(),
                    "description": (self.rm_sec_desc_e.get().strip()
                                    or "Routed Mgmt Uplink"),
                },
                "mgmt_svi": {
                    "enabled":     bool(self.msvi_sec_enabled.get()),
                    "vlan":        self.msvi_sec_vlan_e.get().strip(),
                    "ip":          self.msvi_sec_ip_e.get().strip(),
                    "mask":        self.msvi_sec_mask_e.get().strip(),
                    "description": (self.msvi_sec_desc_e.get().strip()
                                    or "Switch MGMT"),
                },
            }
            drm = self.default_routed_mask_e.get().strip()
            if drm:
                data["default_routed_mask"] = drm
            svis = []
            for r in self.svi_rows:
                vlan = r["vlan"].get().strip()
                if not vlan:
                    continue
                helpers = [h.strip() for h in r["hlp"].get().split(",")
                           if h.strip()]
                entry = {
                    "vlan":             vlan,
                    "description":      r["desc"].get().strip(),
                    "helper_addresses": helpers,
                }
                ip_val = r["ip"].get().strip()
                mask_val = r["mask"].get().strip()
                if ip_val:
                    entry["ip"] = ip_val
                if mask_val:
                    entry["mask"] = mask_val
                svis.append(entry)
            data["svis"] = svis
            networks = []
            for r in self.ospf_net_rows:
                net = r["net"].get().strip()
                if not net:
                    continue
                networks.append({
                    "network":  net,
                    "wildcard": r["wc"].get().strip(),
                    "area":     r["area"].get().strip() or "0",
                })
            passive_ifaces = [
                p.strip() for p in self.ospf_passive_e.get().split(",")
                if p.strip()
            ]
            data["ospf"] = {
                "enabled":             self.ospf_enabled.get(),
                "process_id":          self.ospf_pid_e.get().strip() or "1",
                "passive_default":     self.ospf_passive_default.get(),
                "passive_interfaces":  passive_ifaces,
                "networks":            networks,
            }
            bgp_instances = self._collect_bgp_instances()
            if bgp_instances:
                data["bgp"] = {"instances": bgp_instances}
            acls = self._collect_acls()
            if acls:
                data["acls"] = acls

        self.app.profiles[name] = data
        save_json("profiles.json", self.app.profiles)
        self._refresh(); self.app.gen_tab.refresh_combos()
        _dialog("Saved", f"Profile '{name}' saved.")


# ===================================================================
#  TAB 5 - BASE SETTINGS
# ===================================================================
class BaseTab(ttk.Frame):
    """Side-by-side editor for one or more named base-settings entries.
    The on-disk shape is {"sets": {<name>: {...}}, "default": <name>}."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.fields = {}      # simple entry fields, by key
        self.text_areas = {}  # multi-line text sections, by key
        self.cs_rows = []     # custom config section rows
        self._build()
        # select the default entry on first show
        default = (self.app.base or {}).get("default")
        names = self.app.base_set_names()
        if default and default in names:
            self.lb.select(default)
        elif names:
            self.lb.select(names[0])

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list of base sets --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Base Settings",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="+ Add",      command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Set Default", command=self._set_default).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete",     command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: editor --
        right = ScrollFrame(paned); paned.add(right, weight=1)
        form = right.inner

        _section(form, "Set Details")
        self.name_e = _field(form, "Name")
        self.default_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Use as default for profiles without a base set",
                        variable=self.default_var
                        ).pack(anchor="w", padx=5, pady=(0, 6))

        _section(form, "Credentials")
        self.fields["local_username"] = _field(form, "Local Username", "admin")

        _section(form, "Output Settings")
        ttk.Label(form,
                  text="  Filename template used when saving generated configs.\n"
                  "  Available variables: {{ hostname }}, {{ model }}, "
                  "{{ profile }}, {{ date }}",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.fields["filename_template"] = _field(
            form, "Filename Template",
            "{{ hostname }}_{{ model }}_{{ profile }}")

        sections = [
            ("global_services", "Global Services",
             "no service pad, service timestamps, platform commands, etc."),
            ("mgmt_vrf",        "Management VRF",
             "vrf definition Mgmt-vrf block (if needed)"),
            ("logging",         "Logging",
             "no logging console, logging host, etc."),
            ("aaa",             "AAA Configuration",
             "aaa new-model, authentication, authorization"),
            ("security",        "Security",
             "no ip source-route, no call-home, etc."),
            ("ssh",             "SSH / Crypto",
             "crypto key generate, ip ssh version/time-out"),
            ("switching",       "Switching Features",
             "spanning-tree, VTP, redundancy, vlan dot1q tag native, "
             "memory free low-watermark, transceiver monitoring"),
            ("mgmt_port",       "Management Port",
             "interface GigabitEthernet0/0 config (if needed)"),
            ("line_config",     "Line Configuration",
             "line con 0, line vty 0 15, transport input ssh"),
        ]
        for key, title, hint in sections:
            _section(form, title)
            ttk.Label(form, text=f"  {hint}",
                      style="Hint.TLabel").pack(anchor="w", padx=5)
            self.text_areas[key] = _textarea(form, "", "", h=10)

        _section(form, "Banner LOGIN")
        ttk.Label(form, text="  Enter the banner text only - the app adds "
                  "the 'banner login ^' wrapper.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["banner"] = _textarea(form, "", "", h=20)

        _section(form, "Disabled Port Template")
        ttk.Label(form, text="  Commands applied to every port during the "
                  "'disable all' step.\n"
                  "  Use {{ blackhole_vlan }} or any profile variable.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["disabled_port_template"] = _textarea(form, "", "", h=10)

        _section(form, "Custom Config Sections")
        ttk.Label(form,
                  text="  Add your own config sections (SNMP, NTP, QoS, "
                  "DHCP Snooping, ACLs, etc.).\n"
                  "  Each section is included in every generated config.  "
                  "Use {{ variable }} placeholders - values\n"
                  "  come from the Site Profile's Role Variables.",
                  style="Hint.TLabel").pack(anchor="w", padx=5, pady=(4, 0))

        cs_hdr = ttk.Frame(form)
        cs_hdr.pack(fill="x", padx=5, pady=(6, 2))
        ttk.Button(cs_hdr, text="+ Add Section",
                   command=self._add_cs).pack(side="left")
        ttk.Label(cs_hdr,
                  text="  Position controls where the section appears in "
                  "the generated config.",
                  style="Hint.TLabel").pack(side="left", padx=6)

        self.cs_container = ttk.Frame(form)
        self.cs_container.pack(fill="x", padx=5, pady=(2, 6))

        ttk.Button(form, text="Save Base Settings",
                   command=self._save).pack(padx=5, pady=10, anchor="w")

        self._refresh()

    # -- list helpers --
    def _refresh(self):
        names = self.app.base_set_names()
        default = (self.app.base or {}).get("default")
        # show " (default)" suffix on the default entry so users see it
        labels = [(f"{n}  (default)" if n == default else n) for n in names]
        # _CheckList uses labels as both display and key - to keep things
        # simple we populate with raw names and rely on the editor header
        # / Set Default button to convey which is the default.
        self.lb.populate(names)

    def _on_select(self, name=None):
        if not name:
            return
        b = (self.app.base or {}).get("sets", {}).get(name, {}) or {}

        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.default_var.set(name == (self.app.base or {}).get("default"))

        for key, widget in self.fields.items():
            widget.delete(0, "end")
            widget.insert(0, b.get(key, ""))
        for key, widget in self.text_areas.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", b.get(key, ""))

        self._clear_cs()
        for cs in b.get("custom_sections", []) or []:
            self._add_cs(cs)

    def _clear_cs(self):
        for r in self.cs_rows:
            r["frame"].destroy()
        self.cs_rows.clear()

    def _new(self):
        names = self.app.base_set_names()
        base_name = "New Base"
        candidate = base_name
        i = 1
        while candidate in names:
            i += 1
            candidate = f"{base_name} {i}"
        self.app.base.setdefault("sets", {})[candidate] = {}
        if not self.app.base.get("default"):
            self.app.base["default"] = candidate
        save_json("base_settings.json", self.app.base)
        self._refresh()
        self.lb.select(candidate)

    def _duplicate(self):
        cur = self.lb.get_selected()
        if not cur:
            _dialog("No Selection", "Select a base set to duplicate.")
            return
        data = json.loads(json.dumps(
            self.app.base["sets"].get(cur, {})))
        names = self.app.base_set_names()
        new_name = _copy_name(cur, self.app.base["sets"])
        self.app.base["sets"][new_name] = data
        save_json("base_settings.json", self.app.base)
        self._refresh()
        self.lb.select(new_name)

    def _delete(self):
        names = self.lb.get_checked()
        if not names:
            sel = self.lb.get_selected()
            if not sel:
                return
            names = [sel]
        if (self.app.base or {}).get("sets") and \
                len(self.app.base["sets"]) - len(names) < 1:
            _dialog("Delete",
                    "Cannot delete every base set - at least one must remain.",
                    "warning")
            return
        if len(names) == 1:
            msg = f"Delete base set '{names[0]}'?"
        else:
            msg = f"Delete {len(names)} base sets?\n\n  " + "\n  ".join(names)
        if not _ask("Delete", msg):
            return
        for name in names:
            self.app.base["sets"].pop(name, None)
        # If we removed the default, pick a new one (first alphabetically).
        if self.app.base.get("default") not in self.app.base["sets"]:
            remaining = sorted(self.app.base["sets"].keys(), key=str.lower)
            self.app.base["default"] = remaining[0] if remaining else None
        save_json("base_settings.json", self.app.base)
        self._refresh()
        # Re-select something so the editor isn't stale.
        remaining = self.app.base_set_names()
        if remaining:
            self.lb.select(self.app.base.get("default") or remaining[0])
        # Refresh other tabs so profile dropdowns reflect the change.
        if hasattr(self.app, "profiles_tab"):
            self.app.profiles_tab.refresh_base_sets()

    def _set_default(self):
        sel = self.lb.get_selected()
        if not sel:
            _dialog("No Selection", "Select a base set first.")
            return
        self.app.base["default"] = sel
        save_json("base_settings.json", self.app.base)
        self._refresh()
        self.lb.select(sel)

    def _add_cs(self, data=None):
        frame = ttk.LabelFrame(self.cs_container, padding=5)
        frame.pack(fill="x", pady=(0, 6))

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Name:").pack(side="left")
        name_e = ttk.Entry(top, width=28)
        name_e.pack(side="left", padx=(4, 10))
        _attach_context_menu(name_e)
        ttk.Label(top, text="Position:").pack(side="left")
        pos_cb = ttk.Combobox(top, width=22, state="readonly",
                              values=["Before Interfaces",
                                      "After Interfaces"])
        pos_cb.bind("<MouseWheel>", lambda _e: "break")
        pos_cb.pack(side="left", padx=4)
        pos_cb.set("After Interfaces")
        ttk.Button(top, text="X", width=3, style="Del.TButton",
                   command=lambda f=frame: self._del_cs(f)
                   ).pack(side="right")

        cmds = tk.Text(frame, height=10, font=("Consolas", 9),
                       bg=C["bg_input"], fg=C["fg"],
                       insertbackground=C["fg"],
                       selectbackground=C["sel_bg"],
                       relief="flat", bd=2, wrap="word")
        cmds.pack(fill="x", pady=(4, 0))
        _attach_context_menu(cmds)

        if isinstance(data, dict):
            name_e.insert(0, data.get("name", ""))
            pos = data.get("position", "post-interface")
            pos_cb.set("Before Interfaces"
                       if pos == "pre-interface" else "After Interfaces")
            cmds.insert("1.0", data.get("commands", ""))

        self.cs_rows.append({"frame": frame, "name": name_e,
                             "position": pos_cb, "commands": cmds})

    def _del_cs(self, frame):
        self.cs_rows = [r for r in self.cs_rows if r["frame"] is not frame]
        frame.destroy()

    def _save(self):
        new_name = self.name_e.get().strip()
        if not new_name:
            _dialog("Missing", "Enter a name for this base set.", "warning")
            return

        # collect current editor state into a dict
        data = {}
        for key, widget in self.fields.items():
            data[key] = widget.get().strip()
        for key, widget in self.text_areas.items():
            data[key] = widget.get("1.0", "end").strip()
        cs_list = []
        for r in self.cs_rows:
            cname = r["name"].get().strip()
            if cname:
                pos_val = r["position"].get()
                cs_list.append({
                    "name": cname,
                    "position": ("pre-interface"
                                 if pos_val == "Before Interfaces"
                                 else "post-interface"),
                    "commands": r["commands"].get("1.0", "end").strip(),
                })
        data["custom_sections"] = cs_list

        # rename if the user changed the name field
        old = self.lb.get_selected()
        sets = self.app.base.setdefault("sets", {})
        if old and old != new_name and old in sets:
            del sets[old]
            if self.app.base.get("default") == old:
                self.app.base["default"] = new_name
        sets[new_name] = data

        # default flag
        if self.default_var.get():
            self.app.base["default"] = new_name
        elif self.app.base.get("default") == new_name and len(sets) > 1:
            # User unchecked default on the current entry - pick another.
            others = [n for n in sorted(sets.keys(), key=str.lower)
                      if n != new_name]
            self.app.base["default"] = others[0] if others else new_name

        save_json("base_settings.json", self.app.base)
        self._refresh()
        self.lb.select(new_name)
        if hasattr(self.app, "profiles_tab"):
            self.app.profiles_tab.refresh_base_sets()
        _dialog("Saved", f"Base set '{new_name}' saved.")


# ===================================================================
#  TAB 6 - HOW-TO GUIDE
# ===================================================================
class GuideTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        f = scroll.inner

        def heading(text):
            ttk.Label(f, text=text, font=("Segoe UI", 13, "bold"),
                      foreground=C["accent"], background=C["bg"]
                      ).pack(anchor="w", padx=12, pady=(18, 2))
            ttk.Separator(f).pack(fill="x", padx=12)

        def subheading(text):
            ttk.Label(f, text=text, font=("Segoe UI", 10, "bold"),
                      foreground=C["accent"], background=C["bg"]
                      ).pack(anchor="w", padx=16, pady=(12, 2))

        def body(text):
            lbl = ttk.Label(f, text=text, wraplength=750, justify="left",
                            foreground=C["fg"], background=C["bg"],
                            font=("Segoe UI", 9))
            lbl.pack(anchor="w", padx=20, pady=(2, 2))

        def code(text):
            box = tk.Text(f, height=text.count("\n") + 1,
                          font=("Consolas", 9), wrap="none",
                          bg=C["bg_input"], fg=C["green"],
                          relief="flat", bd=4, padx=6, pady=4)
            box.insert("1.0", text)
            box.configure(state="disabled")
            box.pack(anchor="w", padx=24, pady=(2, 4), fill="x")
            _attach_context_menu(box)

        # ---- Overview ----
        heading("How To Use This App")
        body(
            "This app generates ready-to-paste initial configurations for "
            "Cisco switches and routers (Layer 2 access, Layer 3 distribution, "
            "and L3 edge/BGP). There are two phases:\n\n"
            "ONE-TIME SETUP  (tabs 2-5)\n"
            "Define your switch models, interface roles, site profiles, and "
            "base settings. This only needs to be done once - after that the "
            "definitions are saved and reused.\n\n"
            "DAILY USE  (tab 1 - Generate Config)\n"
            "Pick a model, pick a profile, review port assignments, enter "
            "the per-switch details (hostname, IPs, passwords, SVI IPs, "
            "routed-interface IPs, BGP descriptions, etc.), click "
            "Generate, then copy or save the config.")

        # ---- Recommended order ----
        heading("Recommended Setup Order")
        body(
            "Complete the setup tabs in this order. Each step builds on "
            "the previous one:\n\n"
            "1.  Base Settings   - Global IOS commands shared by all switches\n"
            "2.  Switch Models   - Hardware definitions (port groups)\n"
            "3.  Interface Roles - Reusable per-port command templates\n"
            "4.  Site Profiles   - VLANs, services, L3, and port assignments\n"
            "5.  Generate Config - Use the wizard to build a config")

        # ---- Menu Bar ----
        heading("Menu Bar")
        body(
            "The application has a small menu bar across the top with two "
            "menus:\n\n"
            "File\n"
            "  Export Settings...    Save all your models, roles, profiles, "
            "base settings, and theme as a single ZIP. Use this to back up or "
            "share your setup with teammates.\n"
            "  Import Settings...    Load a previously exported ZIP. "
            "Overwrites the current data.\n"
            "  Recent Profiles       Jump straight to a recently used site "
            "profile in the wizard.\n"
            "  Recent Settings ZIPs  Re-import a recent settings backup.\n"
            "  Recent Configs        Re-open a previously generated config "
            "file in the preview pane.\n\n"
            "Theme\n"
            "  Pick a built-in theme (Default, Coral, Sandstone, Chris, "
            "Voyager, Light) or one of your custom themes. Choose "
            "'Edit Custom Themes...' to create, edit, duplicate, or delete "
            "your own colour palettes.")

        # ---- Step 1: Base Settings ----
        heading("Step 1 - Base Settings Tab")
        body(
            "The Base Settings tab contains IOS commands that are the same "
            "across every switch you configure. Each section is a text area "
            "where you paste raw IOS commands. Leave a section blank to skip "
            "it.\n\n"
            "Sections include: Global Services, Management VRF, Logging, "
            "AAA, Security, SSH/Crypto, Switching Features, Management Port, "
            "Line Configuration, Banner, Disabled Port Template, and "
            "Custom Config Sections for production extras like SNMP, "
            "QoS, DHCP Snooping, ACLs, etc.")

        subheading("Multiple Base Sets")
        body(
            "The Base Settings tab supports multiple named sets. The list on "
            "the left shows every set you have defined. Use the buttons to "
            "manage them:\n\n"
            "  + Add        Create a new base set (gives you a clean editor).\n"
            "  Duplicate    Clone the selected set so you can tweak a copy.\n"
            "  Set Default  Mark the selected set as the fallback used when "
            "a Site Profile does not name a base set, or when the named one "
            "is missing.\n"
            "  Delete       Remove the selected set.\n\n"
            "Each Site Profile picks one base set in the 'Base Settings' "
            "dropdown on the Site Profiles tab. This lets you keep different "
            "AAA / SSH / banner blocks for, say, corporate vs. lab vs. "
            "DMZ sites and select the right one per profile.")

        subheading("Global Services Example")
        code(
            "no service pad\n"
            "service timestamps debug datetime msec localtime\n"
            "service timestamps log datetime msec localtime\n"
            "service password-encryption\n"
            "no service call-home\n"
            "no platform punt-keepalive disable-kernel-core")

        subheading("AAA Example")
        code(
            "aaa new-model\n"
            "aaa authentication login default local\n"
            "aaa authentication enable default enable\n"
            "aaa authorization exec default local")

        subheading("SSH / Crypto Example")
        code(
            "crypto key generate rsa modulus 4096\n"
            "ip ssh version 2\n"
            "ip ssh time-out 60\n"
            "ip ssh authentication-retries 2")

        subheading("Line Configuration Example")
        code(
            "line con 0\n"
            "logging synchronous\n"
            "exec-timeout 15 0\n"
            "line vty 0 15\n"
            "transport input ssh\n"
            "exec-timeout 15 0")

        subheading("Disabled Port Template")
        body(
            "This template is applied to EVERY port on the switch before "
            "your active port assignments override specific ranges. It is "
            "the security baseline - typically shuts down ports and puts "
            "them on a blackhole VLAN.\n\n"
            "You can use {{ variable }} placeholders here. The variable "
            "values come from the Site Profile's Role Variables section. "
            "For example, {{ blackhole_vlan }} will be replaced with the "
            "VLAN number you define in the profile.")
        code(
            "description //Disabled Port\n"
            "switchport access vlan {{ blackhole_vlan }}\n"
            "switchport mode access\n"
            "shutdown\n"
            "spanning-tree bpduguard enable")
        body("Click 'Save Base Settings' when done.")

        subheading("Custom Config Sections")
        body(
            "Use the Custom Config Sections area to add production-ready "
            "config blocks that go beyond the basics - things like SNMP, "
            "NTP, QoS, DHCP Snooping, Dynamic ARP Inspection, ACLs, "
            "TACACS+, and anything else your production environment needs.\n\n"
            "Click '+ Add Section' to create a new block. Each section has:\n\n"
            "  Name - A label for your reference (e.g. 'SNMP Config')\n\n"
            "  Position - Where it appears in the generated config:\n"
            "    'Before Interfaces' - after VLANs, before ports are "
            "configured. Good for DHCP Snooping, DAI, and global "
            "policies that must exist before interface commands.\n"
            "    'After Interfaces' - after all port and VLAN interface "
            "config. Good for SNMP, NTP, ACLs, route-maps, and "
            "monitoring.\n\n"
            "  Commands - Raw IOS commands, just like the other Base "
            "Settings sections. You can use {{ variable }} placeholders "
            "here - values come from the Site Profile's Role Variables.\n\n"
            "You can add as many sections as you need. They are saved "
            "with your Base Settings and included in every generated "
            "config. Delete a section with the X button.")

        subheading("Custom Section Example: SNMP")
        code(
            "snmp-server community {{ snmp_ro_community }} RO\n"
            "snmp-server location {{ site_location }}\n"
            "snmp-server contact {{ contact_email }}")

        body(
            "Note: DNS name-servers, NTP servers, clock timezone, and "
            "summer-time are now configured per-profile in the Site Profiles "
            "tab under 'Services' instead of as a custom Base section.")

        subheading("Custom Section Example: DHCP Snooping")
        code(
            "ip dhcp snooping\n"
            "ip dhcp snooping vlan {{ access_vlan }}\n"
            "no ip dhcp snooping information option\n"
            "ip arp inspection vlan {{ access_vlan }}")

        subheading("Custom Section Example: QoS")
        code(
            "mls qos\n"
            "class-map match-any VOICE\n"
            "match ip dscp ef\n"
            "policy-map QOS-POLICY\n"
            "class VOICE\n"
            "priority percent 30\n"
            "class class-default\n"
            "bandwidth remaining percent 70")

        # ---- Step 2: Switch Models ----
        heading("Step 2 - Switch Models Tab")
        body(
            "Define each switch hardware model your organization uses. "
            "The app needs to know what interfaces exist on each model so "
            "it can disable all ports before selectively enabling the ones "
            "you assign.\n\n"
            "For each model, provide:")
        body(
            "Model Name - The exact Cisco model identifier "
            "(e.g. C9200L-24T-4G-A).\n\n"
            "Provision Type - The string used in the IOS 'switch 1 provision' "
            "command (e.g. c9200l-24t, c9300-24). Leave blank if not needed.\n\n"
            "Port Groups - Each group of interfaces on the switch. "
            "Click '+ Add Port Group' for each group and fill in:")
        body(
            "  Prefix  - The IOS interface prefix including the trailing "
            "slash, e.g. GigabitEthernet1/0/\n"
            "  Start   - First port number in the range\n"
            "  End     - Last port number in the range")

        subheading("Example: C9200L-24T-4G-A")
        code(
            "Model Name:     C9200L-24T-4G-A\n"
            "Provision Type: c9200l-24t\n"
            "\n"
            "Port Group 1:   GigabitEthernet1/0/    Start: 1    End: 24\n"
            "Port Group 2:   GigabitEthernet1/1/    Start: 1    End: 4")

        subheading("Example: C9300-24S-A")
        code(
            "Model Name:     C9300-24S-A\n"
            "Provision Type: c9300-24\n"
            "\n"
            "Port Group 1:   GigabitEthernet1/0/       Start: 1   End: 24\n"
            "Port Group 2:   TenGigabitEthernet1/1/    Start: 1   End: 8\n"
            "Port Group 3:   AppGigabitEthernet1/0/    Start: 1   End: 1\n"
            "Port Group 4:   GigabitEthernet0/          Start: 0   End: 0")
        body("Click 'Save Model' when done.")

        # ---- Step 3: Interface Roles ----
        heading("Step 3 - Interface Roles Tab")
        body(
            "An Interface Role is a reusable block of IOS commands that can "
            "be applied to any interface. Think of it as a template for a "
            "type of port - access port, trunk port, uplink, etc.\n\n"
            "For each role, provide a name and the IOS commands that should "
            "be applied to the interface. The commands go between 'interface "
            "...' and 'exit' - do NOT include those lines.")

        subheading("Using Variables in Roles")
        body(
            "You can include {{ variable }} placeholders in your commands. "
            "These variables are defined in the Site Profile's Role Variables "
            "section, so the same role template can be reused across sites "
            "with different VLAN numbers.\n\n"
            "{{ description }} is always available - it is set per port "
            "assignment in the profile or in the Generate wizard.")

        subheading("Example: Access Port Role")
        code(
            "description {{ description }}\n"
            "switchport access vlan {{ access_vlan }}\n"
            "switchport mode access\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Example: Trunk Uplink Role")
        code(
            "description {{ description }}\n"
            "switchport trunk native vlan {{ native_vlan }}\n"
            "switchport trunk allowed vlan {{ trunk_allowed }}\n"
            "switchport mode trunk\n"
            "no shutdown")

        subheading("Example: Private VLAN Promiscuous Role")
        code(
            "description {{ description }}\n"
            "switchport private-vlan mapping "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport mode private-vlan Promiscuous\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Example: Private VLAN Isolated Role")
        code(
            "description {{ description }}\n"
            "switchport private-vlan host-association "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport private-vlan mapping "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport mode private-vlan host\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Routed Interfaces (Requires IP)")
        body(
            "Tick the 'Requires IP' checkbox for roles that turn an interface "
            "into a layer-3 routed port (no switchport). When a port is "
            "assigned to a role with Requires IP, the wizard's Step 3 grows "
            "an extra grid where you fill in the per-switch IP and mask for "
            "that interface. Use {{ ip }} and {{ mask }} as placeholders in "
            "the role template.")
        code(
            "desc //Routed Uplink\n"
            "no switchport\n"
            "ip address {{ ip }} {{ mask }}\n"
            "no shut")
        body("Click 'Save Role' when done.")

        # ---- Step 4: Site Profiles ----
        heading("Step 4 - Site Profiles Tab")
        body(
            "A Site Profile ties everything together for a specific type of "
            "deployment. It defines the VLANs, the variable values that feed "
            "into your role templates, and which interfaces get which roles.\n\n"
            "Create one profile per deployment type (e.g. 'Office-Floor3', "
            "'Warehouse', 'Data-Center-ToR').")

        subheading("Profile Name & Management VLAN")
        body(
            "Give the profile a descriptive name. The Management VLAN ID is "
            "used to create the 'interface vlanXX' block where the switch's "
            "management IP is assigned (for L2 sites, or L3 sites using "
            "mgmt_style = svi).")

        subheading("Base Settings Selector")
        body(
            "Pick which Base set this profile should use. The dropdown is "
            "populated from the Base Settings tab. If the named set is "
            "missing at generate time, the app falls back to the default "
            "set marked on the Base Settings tab.")

        subheading("Services (DNS / NTP / Clock)")
        body(
            "These per-profile values render as IOS commands in the generated "
            "config so different sites can point at different DNS/NTP "
            "infrastructure without duplicating Base sets:\n\n"
            "  DNS Servers          One or more name-server IPs, comma "
            "separated. Becomes 'ip name-server ...' lines.\n"
            "  NTP Servers          One or more NTP server IPs, comma "
            "separated. Becomes 'ntp server ...' lines.\n"
            "  NTP Source Interface Optional 'ntp source <iface>' line.\n"
            "  NTP Auth Key ID +    Optional MD5 authenticated NTP. Both "
            "  NTP Auth Key         fields are needed to enable authentication.\n"
            "  Clock Timezone       Free-form 'clock timezone ...' value, "
            "e.g. 'EST -5'.\n"
            "  Clock Summer-Time    Free-form 'clock summer-time ...' value, "
            "e.g. 'EDT recurring'.")

        subheading("Credential Defaults")
        body(
            "Optional defaults that pre-fill the matching fields in Generate "
            "Config Step 3 when this profile is selected:\n\n"
            "  Local Username      Becomes 'username <name> ...'.\n"
            "  Local User Password Plain or secret-style password for the "
            "local user.\n"
            "  Enable Secret       Privileged EXEC password.\n\n"
            "These are defaults only - the wizard always lets you change "
            "them per switch, and per-switch edits are not written back "
            "to the profile.")

        subheading("VLAN Definitions")
        body(
            "Paste the raw IOS VLAN commands for this site. This includes "
            "standard VLANs, private VLANs, and any VLAN associations. "
            "These commands are inserted into the config exactly as entered.")
        code(
            "vlan 100\n"
            "name Data\n"
            "vlan 200\n"
            "name Voice\n"
            "vlan 999\n"
            "name Blackhole\n"
            "vlan 500\n"
            "name MGMT")

        subheading("Private VLAN Example")
        code(
            "vlan 300\n"
            "name Isolated-PVLAN\n"
            "private-vlan isolated\n"
            "vlan 301\n"
            "name Primary-PVLAN\n"
            "private-vlan primary\n"
            "private-vlan association 300")

        subheading("Role Variables")
        body(
            "Key/value pairs that replace {{ key }} placeholders in your "
            "Interface Role commands and the Disabled Port Template. Click "
            "'+ Add Variable' for each one.\n\n"
            "Common examples:")
        code(
            "Key: access_vlan        Value: 100\n"
            "Key: native_vlan        Value: 100\n"
            "Key: trunk_allowed      Value: 100,200,500\n"
            "Key: blackhole_vlan     Value: 999\n"
            "Key: pvlan_primary      Value: 301\n"
            "Key: pvlan_isolated     Value: 300")

        subheading("Port Assignments")
        body(
            "Map interface ranges to roles. Each row specifies:\n\n"
            "  Interface(s) - The IOS interface or range text that goes after "
            "'interface'. For a single port: GigabitEthernet1/0/1  For "
            "multiple ports: range GigabitEthernet1/0/1-12\n\n"
            "  Role - Pick one of the roles you defined in the Interface "
            "Roles tab.\n\n"
            "  Description - The port description. This value is available as "
            "{{ description }} in the role template.\n\n"
            "Any ports from the switch model that are NOT assigned here will "
            "be disabled using the Disabled Port Template from Base Settings.")
        code(
            "Interface(s)                         Role           Description\n"
            "range GigabitEthernet1/0/1-20        Access Port    User Ports\n"
            "range GigabitEthernet1/0/21-22       Trunk Uplink   Core Uplink\n"
            "GigabitEthernet1/1/1                 Trunk Uplink   Stack Link")

        subheading("Layer 3 Toggle")
        body(
            "Tick 'Enable Layer 3' for sites that route. This reveals the L3 "
            "editor and tells the generator to emit routing-related blocks "
            "(L3 interfaces, OSPF, BGP, default route, etc.). Leave it off "
            "for plain access-layer switches.")

        subheading("Management Style")
        body(
            "When Layer 3 is on, pick how the switch's management IP is "
            "assigned:\n\n"
            "  svi            Management rides an SVI (same as L2). "
            "Emits 'interface vlan<mgmt_vlan>' with the IP from Step 3.\n"
            "  loopback       Mgmt rides Loopback0. The wizard prompts for "
            "Loopback0 IP/Mask in Step 3.\n"
            "  routed_uplink  Mgmt rides one of the routed uplinks. No "
            "mgmt SVI is emitted; the routed interface holds the mgmt IP.\n\n"
            "'ip default-gateway' is emitted whenever a Default Gateway is "
            "set, regardless of mgmt_style.")

        subheading("Default Routed Mask")
        body(
            "Optional site-wide mask that pre-fills the Mask column of every "
            "routed-interface row in Generate Config Step 3. Useful when "
            "every L3 link at the site uses the same prefix length "
            "(e.g. 255.255.255.252 for /30 point-to-points). Per-switch "
            "overrides in Step 3 always win.")

        subheading("SVIs")
        body(
            "Define the VLANs that need an SVI on every switch at the site. "
            "Each row carries:\n\n"
            "  VLAN          The VLAN ID the SVI belongs to.\n"
            "  Description   Free-form text rendered as the SVI description.\n"
            "  Helpers (CSV) Optional DHCP helper IPs, comma separated. "
            "Each becomes an 'ip helper-address ...' line.\n\n"
            "IPs and masks are entered per-switch in Generate Config "
            "Step 3 under 'SVI IPs'.")

        subheading("OSPF")
        body(
            "Tick 'Enable OSPF' to render a 'router ospf <id>' block. "
            "Fields:\n\n"
            "  Process ID                The OSPF process number.\n"
            "  Passive interface default Tick to emit "
            "'passive-interface default'. Interfaces listed below then become "
            "exceptions (no passive-interface ...). When off, only listed "
            "interfaces are passive.\n"
            "  Passive Interfaces (CSV)  Comma-separated interface names.\n"
            "  Networks                  One row per 'network ... area ...' "
            "statement.\n\n"
            "Router-ID is set per switch in Generate Config Step 3 and "
            "defaults to the Loopback0 IP.")

        subheading("BGP")
        body(
            "Add one BGP instance per local ASN. Each instance renders as "
            "its own 'router bgp <local_asn>' block. Within an instance, "
            "Peer Slots describe BGP neighbours that will exist on every "
            "switch at the site - the peer IP / MD5 key / circuit ID are "
            "filled in per switch in Generate Config Step 3.")
        code(
            "Local ASN: 65000\n"
            "Peer Slots:\n"
            "  Remote ASN: 65001   Description: ISP_Peer\n"
            "  Remote ASN: 65000   Description: Loopback_iBGP")

        subheading("ACLs")
        body(
            "Define named extended ACLs that render in the post-interface "
            "section of the config. Each ACL has a name, type "
            "(currently 'extended'), and a list of rules. Each rule is one "
            "of:\n\n"
            "  remark                Free-form comment line.\n"
            "  permit / deny         A rule with protocol, source + wildcard, "
            "destination + wildcard, and optional 'log'.\n\n"
            "Used for typical edge ACLs like 'block bogons' or 'deny user "
            "subnets to mgmt'.")
        body("Click 'Save Profile' when done.")

        # ---- Daily Use ----
        heading("Daily Use - Generate Config Tab")
        body(
            "Once setup is complete, generating a config is a 3-step wizard:")

        subheading("Wizard Step 1 - Select Model & Site")
        body(
            "Choose the switch model (determines available interfaces) and "
            "the site profile (determines VLANs, roles, and defaults). "
            "Click Next.")

        subheading("Wizard Step 2 - Port Assignments")
        body(
            "The wizard shows all available port groups from the model and "
            "pre-fills port assignments from the profile. You can:\n\n"
            "  - Modify assignments for this specific switch\n"
            "  - Add new rows with '+ Add Row'\n"
            "  - Remove rows with the X button\n"
            "  - Split a range into sub-ranges (e.g. change "
            "'range Gi1/0/1-24' into two rows: "
            "'range Gi1/0/1-12' and 'range Gi1/0/13-24' with different "
            "roles)\n\n"
            "Leave the Role dropdown empty for ranges you want to stay "
            "disabled. Click Next.")

        subheading("Wizard Step 3 - Switch Details")
        body(
            "Fill in the values unique to this specific switch. The fields "
            "shown depend on the profile - Layer 3 profiles unlock extra "
            "sections.\n\n"
            "Core fields (always shown):\n"
            "  Hostname         The switch hostname (e.g. SW-FLOOR3-01).\n"
            "  Local Username   Pre-fills from the profile's Credential "
            "Defaults; edit per switch as needed.\n"
            "  Admin Password   Local admin account password.\n"
            "  Enable Secret    Privileged EXEC password.\n"
            "  Domain Name      IP domain name (also used for SSH key "
            "generation).\n"
            "  Management IP /  Management interface IP and mask. Goes on "
            "  Subnet Mask      the mgmt SVI (L2 / svi mgmt_style), "
            "Loopback0 (loopback), or the routed-uplink interface "
            "(routed_uplink).\n"
            "  Default Gateway  The switch default gateway. Always emits "
            "'ip default-gateway'. For Layer 3 profiles, also auto-emits "
            "'ip route 0.0.0.0 0.0.0.0 <gateway>' unless you supplied your "
            "own default route under Static Routes."
            "\n\n"
            "Layer 3 sections (only when the profile has Layer 3 enabled):\n"
            "  Loopback0 IP/Mask  Shown when mgmt_style = loopback. Becomes "
            "'interface Loopback0' with the given IP/mask.\n"
            "  Router-ID          Optional OSPF router-id. Defaults to "
            "Loopback0 IP if blank.\n"
            "  Routed Interface IPs One row per port assigned to a "
            "Requires-IP role. Fill in the per-switch IP and mask. The Mask "
            "column pre-fills from the profile's Default Routed Mask when "
            "set.\n"
            "  SVI IPs            One row per SVI defined on the profile. "
            "Fill in the per-switch IP/mask for each VLAN's SVI.\n"
            "  Static Routes      Optional 'ip route <prefix> <mask> "
            "<next-hop>' entries with optional descriptions.\n"
            "  BGP Peers          One row per peer slot defined on the "
            "profile. Fill in the neighbour IP, optional MD5 key, and "
            "optional circuit ID per switch.\n\n"
            "Click 'Generate Config' to build the configuration. It appears "
            "in the preview pane on the right. Use 'Copy to Clipboard' to "
            "paste directly into the switch console, or 'Save to File' to "
            "save a .txt file (which is also added to your Recent Configs "
            "menu).")

        # ---- Config Order ----
        heading("Generated Config Order")
        body(
            "The generated config assembles sections in this order. Layer-3 "
            "blocks are only emitted when the profile has Layer 3 enabled.\n\n"
            "Global / Base\n"
            "   Header comment with hostname\n"
            "   configure terminal\n"
            "   Global Services (Base)\n"
            "   hostname\n"
            "   Management VRF (Base)\n"
            "   Logging (Base)\n"
            "   Credentials (enable secret + local username/password)\n"
            "   AAA (Base)\n"
            "   Security (Base)\n"
            "   switch 1 provision (from Model)\n"
            "   ip domain name\n"
            "   ip name-server lines (Profile Services)\n"
            "   clock timezone / summer-time (Profile Services)\n"
            "   NTP authentication + ntp server lines (Profile Services)\n"
            "   SSH / Crypto (Base)\n"
            "   Switching Features (Base)\n\n"
            "VLANs\n"
            "   VLAN Definitions (Profile)\n"
            "   Custom Sections - Before Interfaces (Base)\n"
            "   Disable ALL ports (Model port groups + Disabled Port Template)\n"
            "   VLAN 1 shutdown\n"
            "   Management Port (Base)\n\n"
            "L3 Interfaces  (Layer 3 only)\n"
            "   Loopback0 (when mgmt_style = loopback)\n"
            "   SVIs with per-switch IP / mask / helpers\n\n"
            "Interfaces\n"
            "   Port Assignments (Profile roles applied to interfaces, "
            "including routed interfaces with per-switch IP/mask)\n\n"
            "Management\n"
            "   Management VLAN interface (when L2 or mgmt_style = svi)\n"
            "   ip default-gateway (always when set)\n\n"
            "Post-Interface\n"
            "   Custom Sections - After Interfaces (Base)\n"
            "   Profile ACLs (named extended ACLs)\n\n"
            "Routing  (Layer 3 only)\n"
            "   router ospf <id> block\n"
            "   router bgp <asn> block(s) with neighbours and MD5 auth\n"
            "   Static Routes\n"
            "   Auto default route via Default Gateway (if no user-supplied "
            "0.0.0.0/0)\n\n"
            "Line Config\n"
            "   Line Configuration (Base)\n\n"
            "Banner / End\n"
            "   Banner Login (Base)\n"
            "   end")

        # ---- Tips ----
        heading("Tips")
        body(
            "- All data is saved as JSON files in the data/ folder. You can "
            "back up or share these files with your team, or use File > "
            "Export Settings to bundle them into a single ZIP.\n\n"
            "- You can create multiple Site Profiles for different deployment "
            "types using the same Interface Roles and Switch Models. Each "
            "profile can point at a different Base Settings set if needed.\n\n"
            "- If you need a port configured differently than the profile "
            "default, adjust it in the wizard's Step 2 - the changes only "
            "affect the current config, not the saved profile. The same is "
            "true for credentials and other per-switch fields in Step 3.\n\n"
            "- The Disabled Port Template runs on every port BEFORE your "
            "assignments, so any port you don't explicitly assign a role to "
            "will be shut down and placed on the blackhole VLAN.\n\n"
            "- Leave any Base Settings section blank to omit it entirely "
            "from the generated config.\n\n"
            "- The 'interface' keyword is added automatically. In port "
            "assignments, just enter the range text - e.g. "
            "'range GigabitEthernet1/0/1-12' (not 'interface range ...').\n\n"
            "- A role with 'Requires IP' on it produces an extra row in "
            "Step 3 for every port it's assigned to. Use {{ ip }} and "
            "{{ mask }} in the role template to consume those values.\n\n"
            "- Profile-level Default Routed Mask pre-fills the Mask column "
            "of every routed-interface row in Step 3, so identical /30 "
            "links don't need to be typed in for every switch.\n\n"
            "- For Layer 3 edge sites that talk BGP, define one BGP "
            "instance per local ASN and one peer slot per neighbour role. "
            "Each switch in the wizard fills in peer IP / MD5 key / circuit "
            "ID for that slot.\n\n"
            "- The Default Gateway field is always required. For Layer 3 "
            "profiles, it also seeds the auto 'ip route 0.0.0.0 0.0.0.0' "
            "default route unless you supplied your own under Static "
            "Routes.\n\n"
            "- Use the Theme menu to switch between built-in palettes or "
            "open the custom theme editor to build your own.")


# ===================================================================
#  MAIN APPLICATION
# ===================================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("NetForge Config Generator")
        root.geometry("1050x780")
        root.minsize(900, 600)

        # Set the window / taskbar icon
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "NetForge.ico")
        if os.path.isfile(icon_path):
            root.iconbitmap(icon_path)

        apply_theme(root)

        # custom menu bar (frame-based so it's fully theme-able on Windows)
        self.menubar_frame = tk.Frame(root, bg=C["bg2"], bd=0,
                                      relief="flat")
        self.menubar_frame.pack(side="top", fill="x")

        menu_kw = dict(bg=C["bg2"], fg=C["fg"], font=("Segoe UI", 9),
                        activebackground=C["border"],
                        activeforeground=C["fg"], bd=0, relief="flat",
                        highlightthickness=0, padx=8, pady=4)
        drop_kw = dict(tearoff=0, bg=C["bg2"], fg=C["fg"],
                        activebackground=C["border"],
                        activeforeground=C["fg"])

        file_mb = tk.Menubutton(self.menubar_frame, text="File", **menu_kw)
        file_mb.pack(side="left")
        file_menu = tk.Menu(file_mb, **drop_kw)
        file_menu.add_command(label="Export Settings...",
                              command=self._export_settings)
        file_menu.add_command(label="Import Settings...",
                              command=self._import_settings)
        file_menu.add_separator()
        self._recent_profiles_menu = tk.Menu(file_menu, **drop_kw)
        self._recent_zips_menu     = tk.Menu(file_menu, **drop_kw)
        self._recent_configs_menu  = tk.Menu(file_menu, **drop_kw)
        file_menu.add_cascade(label="Recent Profiles",
                              menu=self._recent_profiles_menu)
        file_menu.add_cascade(label="Recent Settings ZIPs",
                              menu=self._recent_zips_menu)
        file_menu.add_cascade(label="Recent Configs",
                              menu=self._recent_configs_menu)
        file_mb.configure(menu=file_menu)
        self._rebuild_recent_menus()

        self._theme_var = tk.StringVar(value=self._current_theme_id())
        self._theme_mb = tk.Menubutton(self.menubar_frame, text="Theme",
                                       **menu_kw)
        self._theme_mb.pack(side="left")
        self._build_theme_menu()

        # load data
        self.models   = load_json("models.json",        {})
        self.roles    = load_json("roles.json",          {})
        self.profiles = load_json("profiles.json",       {})
        self.base     = load_base_settings()

        # tabs
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=5, pady=5)

        self.gen_tab = GenerateTab(self.nb, self)
        self.nb.add(self.gen_tab,  text="  Generate Config  ")

        self.models_tab   = ModelsTab(self.nb, self)
        self.roles_tab    = RolesTab(self.nb, self)
        self.profiles_tab = ProfilesTab(self.nb, self)
        self.base_tab     = BaseTab(self.nb, self)
        self.nb.add(self.models_tab,   text="  Switch Models  ")
        self.nb.add(self.roles_tab,    text="  Interface Roles  ")
        self.nb.add(self.profiles_tab, text="  Site Profiles  ")
        self.nb.add(self.base_tab,     text="  Base Settings  ")
        self.nb.add(GuideTab(self.nb, self), text="  How-To Guide  ")

    # ---- export / import settings ----
    _SETTINGS_FILES = [
        "models.json", "roles.json", "profiles.json", "base_settings.json",
        "theme.json",
    ]

    def _export_settings(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            initialfile="NetForge_Settings.zip",
            filetypes=[("ZIP Archive", "*.zip"), ("All", "*.*")])
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in self._SETTINGS_FILES:
                    fp = os.path.join(DATA_DIR, name)
                    if os.path.exists(fp):
                        zf.write(fp, name)
            _dialog("Exported", f"Settings exported to:\n{path}")
        except Exception as exc:
            _dialog("Export Error", str(exc), "error")

    def _import_settings(self):
        path = filedialog.askopenfilename(
            filetypes=[("ZIP Archive", "*.zip"), ("All", "*.*")])
        if path:
            self._import_settings_from_path(path)

    def _import_settings_from_path(self, path):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                valid = [n for n in names if n in self._SETTINGS_FILES]
                if not valid:
                    _dialog("Invalid",
                            "The selected ZIP does not contain NetForge settings.",
                            "warning")
                    return
                if not _ask(
                        "Import Settings",
                        f"This will overwrite your current settings:\n\n"
                        f"  {', '.join(valid)}\n\n"
                        "Continue?"):
                    return
                os.makedirs(DATA_DIR, exist_ok=True)
                for name in valid:
                    zf.extract(name, DATA_DIR)
        except zipfile.BadZipFile:
            _dialog("Import Error", "The selected file is not a valid ZIP.",
                    "error")
            return
        except Exception as exc:
            _dialog("Import Error", str(exc), "error")
            return

        self._push_recent("zips", path)
        # reload data and refresh all tabs
        self.models   = load_json("models.json",       {})
        self.roles    = load_json("roles.json",         {})
        self.profiles = load_json("profiles.json",      {})
        self.base     = load_base_settings()
        self._rebuild_tabs()
        _dialog("Imported",
                "Settings imported successfully.\nAll tabs have been refreshed.")

    # ---- recent items -------------------------------------------------------

    def _load_recents(self):
        data = load_json("recent.json", {})
        return {"profiles": data.get("profiles", []),
                "zips":     data.get("zips",     []),
                "configs":  data.get("configs",  [])}

    def _save_recents(self, data):
        save_json("recent.json", data)

    def _push_recent(self, key, value):
        """Prepend *value* to the *key* recents list and persist."""
        data = self._load_recents()
        lst  = [v for v in data.get(key, []) if v != value]
        lst.insert(0, value)
        data[key] = lst[:_RECENT_MAX]
        self._save_recents(data)
        self._rebuild_recent_menus()

    def _rebuild_recent_menus(self):
        """Repopulate all three Recent cascade menus from saved recents."""
        data = self._load_recents()
        specs = [
            (self._recent_profiles_menu, "profiles", self._open_recent_profile),
            (self._recent_zips_menu,     "zips",     self._open_recent_zip),
            (self._recent_configs_menu,  "configs",  self._open_recent_config),
        ]
        for menu, key, handler in specs:
            menu.delete(0, "end")
            items = data.get(key, [])
            if items:
                for item in items:
                    lbl = (os.path.basename(item)
                           if key in ("zips", "configs") else item)
                    menu.add_command(label=lbl,
                                     command=lambda v=item: handler(v))
            else:
                menu.add_command(label="(none)", state="disabled")

    def _open_recent_profile(self, name):
        if name not in self.profiles:
            _dialog("Recent Profile",
                    f"Profile '{name}' no longer exists.", "warning")
            return
        self.nb.select(0)
        self.gen_tab.profile_cb.set(name)

    def _open_recent_zip(self, path):
        if not os.path.isfile(path):
            _dialog("Recent File", f"File not found:\n{path}", "warning")
            return
        self._import_settings_from_path(path)

    def _open_recent_config(self, path):
        if not os.path.isfile(path):
            _dialog("Recent Config", f"File not found:\n{path}", "warning")
            return
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception as exc:
            _dialog("Open Error", str(exc), "error")
            return
        # navigate to Generate Config tab, step 3, and load into preview
        self.nb.select(0)
        self.gen_tab._show_step(2)
        self.gen_tab.preview.configure(state="normal")
        self.gen_tab.preview.delete("1.0", "end")
        self.gen_tab.preview.insert("1.0", text)
        self.gen_tab.preview.configure(state="disabled")

    # -------------------------------------------------------------------------

    def base_set_names(self):
        """Sorted list of available base-settings entries."""
        return sorted((self.base or {}).get("sets", {}).keys(),
                      key=str.lower)

    def resolved_base(self, profile):
        """Return the base dict that should be used for *profile*. Falls
        back to the default entry when the profile's base_set is missing
        or unknown."""
        name = (profile or {}).get("base_set") or None
        return resolve_base(self.base, name)

    def _rebuild_tabs(self):
        """Destroy and recreate all tabs to reflect imported data or theme."""
        for tab in list(self.nb.tabs()):
            w = self.root.nametowidget(tab)
            self.nb.forget(w)
            w.destroy()

        self.gen_tab      = GenerateTab(self.nb, self)
        self.models_tab   = ModelsTab(self.nb, self)
        self.roles_tab    = RolesTab(self.nb, self)
        self.profiles_tab = ProfilesTab(self.nb, self)
        self.base_tab     = BaseTab(self.nb, self)

        self.nb.add(self.gen_tab,      text="  Generate Config  ")
        self.nb.add(self.models_tab,   text="  Switch Models  ")
        self.nb.add(self.roles_tab,    text="  Interface Roles  ")
        self.nb.add(self.profiles_tab, text="  Site Profiles  ")
        self.nb.add(self.base_tab,     text="  Base Settings  ")
        self.nb.add(GuideTab(self.nb, self), text="  How-To Guide  ")
        self.nb.select(0)

    @staticmethod
    def _current_theme_id():
        saved = load_json("theme.json", {})
        return saved.get("theme", "default")

    def _build_theme_menu(self):
        """Build (or rebuild) the Theme drop-down, including custom themes."""
        drop_kw = dict(tearoff=0, bg=C["bg2"], fg=C["fg"],
                       activebackground=C["border"],
                       activeforeground=C["fg"])
        theme_menu = tk.Menu(self._theme_mb, **drop_kw)
        # built-in themes
        for tid, t in THEMES.items():
            theme_menu.add_radiobutton(
                label=t["name"], variable=self._theme_var, value=tid,
                command=lambda tid=tid: self._switch_theme(tid))
        # custom themes
        custom = load_json("theme.json", {}).get("custom_themes", {})
        if custom:
            theme_menu.add_separator()
            for tid, t in custom.items():
                theme_menu.add_radiobutton(
                    label=t.get("name", tid),
                    variable=self._theme_var, value=tid,
                    command=lambda tid=tid: self._switch_theme(tid))
        theme_menu.add_separator()
        theme_menu.add_command(label="Edit Custom Themes…",
                               command=self._open_theme_editor)
        self._theme_mb.configure(menu=theme_menu)
        self._theme_menu = theme_menu

    def _open_theme_editor(self):
        _ThemeEditorDialog(self, on_close=self._build_theme_menu)

    def _refresh_menubar_colors(self):
        """Re-apply current C colours to every widget in the menu bar."""
        self.menubar_frame.configure(bg=C["bg2"])
        for w in self.menubar_frame.winfo_children():
            w.configure(bg=C["bg2"], fg=C["fg"],
                        activebackground=C["border"],
                        activeforeground=C["fg"])
            try:
                sub = w.cget("menu")
                if sub:
                    self.root.nametowidget(sub).configure(
                        bg=C["bg2"], fg=C["fg"],
                        activebackground=C["border"],
                        activeforeground=C["fg"])
            except Exception:
                pass
        _cascade_kw = dict(bg=C["bg2"], fg=C["fg"],
                           activebackground=C["border"],
                           activeforeground=C["fg"])
        for _m in (self._recent_profiles_menu, self._recent_zips_menu,
                   self._recent_configs_menu):
            _m.configure(**_cascade_kw)

    def _switch_theme(self, tid):
        all_t = {**THEMES,
                 **load_json("theme.json", {}).get("custom_themes", {})}
        if tid not in all_t:
            return
        C.update(all_t[tid])
        _save_theme(tid)
        self._theme_var.set(tid)
        apply_theme(self.root)
        self._refresh_menubar_colors()
        self._rebuild_tabs()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
