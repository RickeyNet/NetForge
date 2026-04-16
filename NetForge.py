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
import tkinter as tk
import zipfile
from tkinter import ttk, filedialog, messagebox, scrolledtext
from jinja2 import Environment

VERSION = "1.2.2"


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
        "bg":           "#868f76",
        "bg2":          "#a3ac9a",
        "bg_input":     "#adab99",
        "fg":           "#4a4a3a",
        "fg_dim":       "#4b4938",
        "accent":       "#5c2e2e",
        "accent_hover": "#a06c6c",
        "border":       "#b0ad94",
        "green":        "#5a7a4a",
        "red":          "#851616",
        "red_hover":    "#703B3B",
        "sel_bg":       "#4b493d",
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
}

# Active colour palette - starts with default, updated by _load_theme()
C = dict(THEMES["default"])


def _load_theme():
    """Load the saved theme preference and apply it to C."""
    saved = load_json("theme.json", {})
    tid = saved.get("theme", "default")
    if tid in THEMES:
        C.update(THEMES[tid])


def _save_theme(tid):
    """Persist the selected theme id."""
    save_json("theme.json", {"theme": tid})


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


def _dark_listbox(parent, **kw):
    return tk.Listbox(parent, font=("Consolas", 10),
                      bg=C["bg_input"], fg=C["fg"],
                      selectbackground=C["border"],
                      selectforeground=C["fg"],
                      relief="flat", bd=2, **kw)


# ===================================================================
#  CONFIG RENDERER
# ===================================================================
def render_config(model, profile, roles, base, sw):
    """Build the full IOS config string from all parts.

    *model*    - switch model dict   (port_groups, provision)
    *profile*  - site profile dict   (vlan_definitions, role_variables,
                                      port_assignments, mgmt_vlan)
    *roles*    - all roles dict      {name: {commands: ...}}
    *base*     - base settings dict  (text-area sections)
    *sw*       - per-switch dict     (hostname, enable_secret, admin_password,
                                      domain_name, mgmt_ip, mgmt_mask,
                                      default_gateway)
    """
    env = Environment()
    role_vars = profile.get("role_variables", {})
    parts = []                       # each entry is one config "block"

    def add(text):
        text = text.strip()
        if text:
            parts.append(text)

    # -- header / global services -----------------------------------------
    parts.append(f"!\n! {sw['hostname']} - Generated Configuration\n!")
    parts.append("configure terminal")
    add(base.get("global_services", ""))

    # -- hostname ---------------------------------------------------------
    parts.append(f"hostname {sw['hostname']}")

    # -- management VRF ---------------------------------------------------
    add(base.get("mgmt_vrf", ""))

    # -- logging ----------------------------------------------------------
    add(base.get("logging", ""))

    # -- credentials ------------------------------------------------------
    parts.append(f"enable secret {sw['enable_secret']}")
    username = base.get("local_username", "admin") or "admin"
    parts.append(f"username {username} privilege 0 secret "
                 f"{sw['admin_password']}")

    # -- AAA --------------------------------------------------------------
    add(base.get("aaa", ""))

    # -- security ---------------------------------------------------------
    add(base.get("security", ""))

    # -- switch provision (from model) ------------------------------------
    provision = model.get("provision", "").strip()
    stack = model.get("stack_members", 1)
    if provision:
        for member in range(1, stack + 1):
            parts.append(f"switch {member} provision {provision}")

    # -- domain name ------------------------------------------------------
    parts.append(f"ip domain name {sw['domain_name']}")

    # -- SSH / crypto -----------------------------------------------------
    add(base.get("ssh", ""))

    # -- switching features (STP, VTP, redundancy, etc.) ------------------
    add(base.get("switching", ""))

    # -- VLAN definitions from profile ------------------------------------
    add(profile.get("vlan_definitions", ""))

    # -- custom sections: before interfaces -------------------------------
    for cs in base.get("custom_sections", []):
        if cs.get("position") == "pre-interface":
            cmds = cs.get("commands", "").strip()
            if cmds:
                try:
                    cmds = env.from_string(cmds).render(**role_vars)
                except Exception:
                    pass
                add(cmds)

    # -- disable ALL ports first (from model port groups) -----------------
    dis_tpl = base.get("disabled_port_template", "").strip()
    all_pgs = expand_port_groups_for_stack(
        model.get("port_groups", []), stack)
    if dis_tpl and all_pgs:
        try:
            rendered_dis = env.from_string(dis_tpl).render(**role_vars)
        except Exception:
            rendered_dis = dis_tpl

        for pg in all_pgs:
            # Skip the OOB management port (e.g. GigabitEthernet0/0) —
            # it's a routed port that doesn't accept switchport commands
            # and is configured separately via the mgmt_port setting.
            if pg.get("prefix", "").startswith("GigabitEthernet0/"):
                continue
            if pg["start"] == pg["end"]:
                hdr = f"interface {pg['prefix']}{pg['start']}"
            else:
                hdr = f"interface range {pg['prefix']}{pg['start']}-{pg['end']}"
            parts.append(f"{hdr}\n{rendered_dis}\nexit")

    # -- VLAN 1 shutdown --------------------------------------------------
    parts.append("interface vlan1\nno ip address\nshutdown\nexit")

    # -- management port (Gi0/0, etc.) ------------------------------------
    # Only apply the default mgmt_port base setting when the user has NOT
    # assigned a role to GigabitEthernet0/x via the port-assignment table.
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
            oob_ip = sw.get("oob_ip", "")
            oob_mask = sw.get("oob_mask", "")
            if oob_ip and oob_mask:
                parts.append(f"interface {iface}\n"
                             f"ip address {oob_ip} {oob_mask}\n"
                             f"negotiation auto\nexit")
            else:
                mgmt_cmds = base.get("mgmt_port", "").strip()
                if mgmt_cmds:
                    parts.append(f"interface {iface}\n{mgmt_cmds}")

    # -- port assignments from profile (override disabled ports) ----------
    for pa in profile.get("port_assignments", []):
        if not pa.get("role") or pa["role"] == "unassigned":
            continue
        role = roles.get(pa.get("role", ""), {})
        cmds = role.get("commands", "")
        try:
            rendered = env.from_string(cmds).render(
                description=pa.get("description", ""), **role_vars)
        except Exception:
            rendered = cmds
        iface = pa.get("interfaces", "")
        parts.append(f"interface {iface}\n{rendered}\nexit")

    # -- management VLAN interface ----------------------------------------
    mgmt_vlan = profile.get("mgmt_vlan", "1")
    parts.append(f"interface vlan{mgmt_vlan}\n"
                 f"description //Switch MGMT\n"
                 f"ip address {sw['mgmt_ip']} {sw['mgmt_mask']}\n"
                 f"exit")

    # -- default gateway --------------------------------------------------
    parts.append(f"ip default-gateway {sw['default_gateway']}")

    # -- custom sections: after interfaces --------------------------------
    for cs in base.get("custom_sections", []):
        if cs.get("position") == "post-interface":
            cmds = cs.get("commands", "").strip()
            if cmds:
                try:
                    cmds = env.from_string(cmds).render(**role_vars)
                except Exception:
                    pass
                add(cmds)

    # -- line config ------------------------------------------------------
    add(base.get("line_config", ""))

    # -- banner -----------------------------------------------------------
    banner = base.get("banner", "").strip()
    if banner:
        parts.append(f"banner login ^\n{banner}\n^")

    # -- end --------------------------------------------------------------
    parts.append("end")

    return "\n\n".join(parts) + "\n"


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
        cur = self.app.base.get("port_display_mode", "range")
        self.pa_display_cb.set(
            "Individual Ports" if cur == "listed" else "Range")
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

        # -- left: form --
        left = ScrollFrame(paned)
        paned.add(left, weight=1)
        form = left.inner

        ttk.Label(form, text="Step 3 - Enter Per-Switch Details",
                  style="Sec.TLabel").pack(anchor="w", padx=5, pady=(5, 10))

        self.hostname  = _field(form, "Hostname")
        self.secret    = _field(form, "Enable Secret")
        self.password  = _field(form, "Admin Password")
        self.domain    = _field(form, "Domain Name")
        self.mgmt_ip   = _field(form, "Management IP")
        self.mgmt_mask = _field(form, "Subnet Mask", "255.255.255.0")
        self.gateway   = _field(form, "Default Gateway")

        # OOB management port (Gi0/0) - only shown for models that have one
        self.oob_frame = ttk.Frame(form)
        _section(self.oob_frame, "OOB Management Port (Gi0/0)")
        ttk.Label(self.oob_frame,
                  text="Optional - leave blank to use base settings default.",
                  style="Hint.TLabel").pack(anchor="w", padx=5, pady=(2, 0))
        self.oob_ip   = _field(self.oob_frame, "OOB IP Address")
        self.oob_mask = _field(self.oob_frame, "OOB Subnet Mask")

        # -- right: preview --
        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        ttk.Label(right, text="Config Preview",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=(4, 0))
        self.preview = scrolledtext.ScrolledText(
            right, wrap="none", font=("Consolas", 10),
            bg=C["bg_input"], fg=C["green"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2)
        self.preview.pack(fill="both", expand=True, padx=4, pady=4)
        _attach_context_menu(self.preview)

    # --------------------------------------------------------- step logic
    def _step1_next(self):
        mn = self.model_cb.get()
        pn = self.profile_cb.get()
        if not mn or mn not in self.app.models:
            messagebox.showwarning("Missing", "Select a switch model.")
            return
        if not pn or pn not in self.app.profiles:
            messagebox.showwarning("Missing", "Select a site profile.")
            return
        self._populate_step2(mn, pn)
        # auto-fill domain name from profile
        profile = self.app.profiles[pn]
        domain = profile.get("domain_name", "")
        if domain:
            self.domain.delete(0, "end")
            self.domain.insert(0, domain)
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
        self._show_step(2)

    def _step3_back(self):
        self.preview.delete("1.0", "end")
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

    def _sw_dict(self):
        return {
            "hostname":        self.hostname.get().strip(),
            "enable_secret":   self.secret.get().strip(),
            "admin_password":  self.password.get().strip(),
            "domain_name":     self.domain.get().strip(),
            "mgmt_ip":         self.mgmt_ip.get().strip(),
            "mgmt_mask":       self.mgmt_mask.get().strip(),
            "default_gateway": self.gateway.get().strip(),
            "oob_ip":          self.oob_ip.get().strip(),
            "oob_mask":        self.oob_mask.get().strip(),
        }

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
            messagebox.showwarning("Missing", "Hostname is required.")
            return

        # build a profile copy with the wizard's port assignments
        profile = dict(self.app.profiles[pn])
        profile["port_assignments"] = self._get_pa_list()

        try:
            cfg = render_config(self.app.models[mn], profile,
                                self.app.roles, self.app.base, sw)
        except Exception as exc:
            messagebox.showerror("Render Error", str(exc))
            return

        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", cfg)

    def _save(self):
        txt = self.preview.get("1.0", "end").strip()
        if not txt:
            messagebox.showinfo("Empty", "Generate a config first.")
            return
        name = self.hostname.get().strip() or "switch_config"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile=f"{name}_config.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def _copy(self):
        txt = self.preview.get("1.0", "end").strip()
        if not txt:
            messagebox.showinfo("Empty", "Generate a config first.")
            return
        self.clipboard_clear()
        self.clipboard_append(txt)
        messagebox.showinfo("Copied", "Config copied to clipboard.")


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
        self.lb = _dark_listbox(left, width=22)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",    command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete", command=self._delete,
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
        self.lb.delete(0, "end")
        for n in self.app.models:
            self.lb.insert("end", n)

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
    def _on_select(self, _=None):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
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
        self.lb.selection_clear(0, "end")
        self.name_e.delete(0, "end")
        self.provision_e.delete(0, "end")
        self.stack_e.delete(0, "end"); self.stack_e.insert(0, "1")
        self._clear_pg()

    def _delete(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete model '{name}'?"):
            del self.app.models[name]
            save_json("models.json", self.app.models)
            self._refresh(); self._new()
            self.app.gen_tab.refresh_combos()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a model name."); return
        pgs = []
        for r in self.pg_rows:
            try:
                s, e = int(r["start"].get()), int(r["end"].get())
            except ValueError:
                messagebox.showwarning("Invalid",
                                       "Start / End must be numbers."); return
            pgs.append({"prefix": r["prefix"].get().strip(),
                        "start": s, "end": e})
        sel = self.lb.curselection()
        if sel:
            old = self.lb.get(sel[0])
            if old != name and old in self.app.models:
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
        messagebox.showinfo("Saved", f"Model '{name}' saved.")


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
        self.lb = _dark_listbox(left, width=22)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",    command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete", command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: edit --
        right = ScrollFrame(paned); paned.add(right, weight=1)
        form = right.inner
        _section(form, "Role Details")
        self.name_e = _field(form, "Role Name")

        _section(form, "IOS Commands")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Enter the IOS commands for this interface role.\n"
                       "  Use {{ variable }} for dynamic values defined in\n"
                       "  the Site Profile.  {{ description }} is always\n"
                       "  available (set per port assignment)."
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
        self.lb.delete(0, "end")
        for n in self.app.roles:
            self.lb.insert("end", n)

    def _on_select(self, _=None):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        role = self.app.roles.get(name, {})
        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.cmds.delete("1.0", "end")
        self.cmds.insert("1.0", role.get("commands", ""))

    def _new(self):
        self.lb.selection_clear(0, "end")
        self.name_e.delete(0, "end")
        self.cmds.delete("1.0", "end")

    def _delete(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete role '{name}'?"):
            del self.app.roles[name]
            save_json("roles.json", self.app.roles)
            self._refresh(); self._new()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a role name."); return
        sel = self.lb.curselection()
        if sel:
            old = self.lb.get(sel[0])
            if old != name and old in self.app.roles:
                del self.app.roles[old]
        self.app.roles[name] = {
            "commands": self.cmds.get("1.0", "end").strip()}
        save_json("roles.json", self.app.roles)
        self._refresh()
        messagebox.showinfo("Saved", f"Role '{name}' saved.")


# ===================================================================
#  TAB 4 - SITE PROFILES
# ===================================================================
class ProfilesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.var_rows = []
        self.pa_rows  = []
        self._build()

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Site Profiles",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.lb = _dark_listbox(left, width=22)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_select)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",    command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete", command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: edit --
        right = ScrollFrame(paned); paned.add(right, weight=1)
        form = right.inner

        _section(form, "Profile Details")
        self.name_e = _field(form, "Profile Name")
        self.domain_e = _field(form, "Domain Name")
        self.mgmt_vlan_e = _field(form, "Management VLAN ID")

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

        ttk.Button(form, text="Save Profile",
                   command=self._save).pack(padx=5, pady=10, anchor="w")
        self._refresh()

    # -- list helpers --
    def _refresh(self):
        self.lb.delete(0, "end")
        for n in self.app.profiles:
            self.lb.insert("end", n)

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

    # -- actions --
    def _on_select(self, _=None):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        p = self.app.profiles.get(name, {})

        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.domain_e.delete(0, "end")
        self.domain_e.insert(0, p.get("domain_name", ""))
        self.mgmt_vlan_e.delete(0, "end")
        self.mgmt_vlan_e.insert(0, p.get("mgmt_vlan", ""))

        self.vlans_text.delete("1.0", "end")
        self.vlans_text.insert("1.0", p.get("vlan_definitions", ""))

        self._clear_vars()
        for k, v in p.get("role_variables", {}).items():
            self._add_var((k, v))

        self._clear_pa()
        for pa in p.get("port_assignments", []):
            self._add_pa(pa)

    def _new(self):
        self.lb.selection_clear(0, "end")
        self.name_e.delete(0, "end")
        self.domain_e.delete(0, "end")
        self.mgmt_vlan_e.delete(0, "end")
        self.vlans_text.delete("1.0", "end")
        self._clear_vars(); self._clear_pa()

    def _delete(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
            del self.app.profiles[name]
            save_json("profiles.json", self.app.profiles)
            self._refresh(); self._new()
            self.app.gen_tab.refresh_combos()

    def _save(self):
        name = self.name_e.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a profile name."); return

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

        sel = self.lb.curselection()
        if sel:
            old = self.lb.get(sel[0])
            if old != name and old in self.app.profiles:
                del self.app.profiles[old]

        self.app.profiles[name] = {
            "domain_name":      self.domain_e.get().strip(),
            "mgmt_vlan":        self.mgmt_vlan_e.get().strip(),
            "vlan_definitions": self.vlans_text.get("1.0", "end").strip(),
            "role_variables":   role_vars,
            "port_assignments": pas,
        }
        save_json("profiles.json", self.app.profiles)
        self._refresh(); self.app.gen_tab.refresh_combos()
        messagebox.showinfo("Saved", f"Profile '{name}' saved.")


# ===================================================================
#  TAB 5 - BASE SETTINGS
# ===================================================================
class BaseTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.fields = {}      # simple entry fields
        self.text_areas = {}  # multi-line text sections
        self.cs_rows = []     # custom config section rows
        self._build()

    def _build(self):
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        form = scroll.inner

        b = self.app.base

        # simple field
        _section(form, "Credentials")
        self.fields["local_username"] = _field(
            form, "Local Username", b.get("local_username", "admin"))

        # text-area sections - order matches a typical IOS config
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
            self.text_areas[key] = _textarea(form, "", b.get(key, ""), h=10)

        # banner (just the text - app wraps with banner login ^ ... ^)
        _section(form, "Banner LOGIN")
        ttk.Label(form, text="  Enter the banner text only - the app adds "
                  "the 'banner login ^' wrapper.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["banner"] = _textarea(
            form, "", b.get("banner", ""), h=20)

        # disabled-port template
        _section(form, "Disabled Port Template")
        ttk.Label(form, text="  Commands applied to every port during the "
                  "'disable all' step.\n"
                  "  Use {{ blackhole_vlan }} or any profile variable.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["disabled_port_template"] = _textarea(
            form, "", b.get("disabled_port_template", ""), h=10)

        # -- custom config sections (user-defined production blocks) --
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

        # load existing custom sections
        for cs in b.get("custom_sections", []):
            self._add_cs(cs)

        ttk.Button(form, text="Save Base Settings",
                   command=self._save).pack(padx=5, pady=10, anchor="w")

    # -- custom section helpers --
    def _add_cs(self, data=None):
        """Add a custom config section block."""
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
        data = {}
        for key, widget in self.fields.items():
            data[key] = widget.get().strip()
        for key, widget in self.text_areas.items():
            data[key] = widget.get("1.0", "end").strip()
        # collect custom sections
        cs_list = []
        for r in self.cs_rows:
            name = r["name"].get().strip()
            if name:
                pos_val = r["position"].get()
                cs_list.append({
                    "name": name,
                    "position": ("pre-interface"
                                 if pos_val == "Before Interfaces"
                                 else "post-interface"),
                    "commands": r["commands"].get("1.0", "end").strip(),
                })
        data["custom_sections"] = cs_list

        self.app.base = data
        save_json("base_settings.json", data)
        messagebox.showinfo("Saved", "Base settings saved.")


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
            "Cisco switches. There are two phases:\n\n"
            "ONE-TIME SETUP  (tabs 2-5)\n"
            "Define your switch models, interface roles, site profiles, and "
            "base settings. This only needs to be done once - after that the "
            "definitions are saved and reused.\n\n"
            "DAILY USE  (tab 1 - Generate Config)\n"
            "Pick a model, pick a profile, review port assignments, enter "
            "the per-switch details (hostname, IPs, passwords), click "
            "Generate, then copy or save the config.")

        # ---- Recommended order ----
        heading("Recommended Setup Order")
        body(
            "Complete the setup tabs in this order. Each step builds on "
            "the previous one:\n\n"
            "1.  Base Settings   - Global IOS commands shared by all switches\n"
            "2.  Switch Models   - Hardware definitions (port groups)\n"
            "3.  Interface Roles - Reusable per-port command templates\n"
            "4.  Site Profiles   - VLANs, variables, and port assignments\n"
            "5.  Generate Config - Use the wizard to build a config")

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
            "Custom Config Sections for production extras like SNMP, NTP, "
            "QoS, DHCP Snooping, ACLs, etc.")

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

        subheading("Custom Section Example: NTP")
        code(
            "ntp server 10.0.0.1\n"
            "ntp server 10.0.0.2\n"
            "clock timezone EST -5\n"
            "clock summer-time EDT recurring")

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
            "management IP is assigned.")

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
            "Fill in the values unique to this specific switch:\n\n"
            "  Hostname         - The switch hostname (e.g. SW-FLOOR3-01)\n"
            "  Enable Secret    - The privileged EXEC password\n"
            "  Admin Password   - The local admin account password\n"
            "  Domain Name      - IP domain name for SSH key generation\n"
            "  Management IP    - The switch management interface IP\n"
            "  Subnet Mask      - Management subnet mask (default 255.255.255.0)\n"
            "  Default Gateway  - The switch default gateway IP\n\n"
            "Click 'Generate Config' to build the configuration. It appears "
            "in the preview pane on the right. Use 'Copy to Clipboard' to "
            "paste directly into the switch console, or 'Save to File' to "
            "save a .txt file.")

        # ---- Config Order ----
        heading("Generated Config Order")
        body(
            "The generated config assembles sections in this order:\n\n"
            " 1.  Header comment with hostname\n"
            " 2.  configure terminal\n"
            " 3.  Global Services (from Base Settings)\n"
            " 4.  hostname\n"
            " 5.  Management VRF (from Base Settings)\n"
            " 6.  Logging (from Base Settings)\n"
            " 7.  Credentials (enable secret + admin user)\n"
            " 8.  AAA (from Base Settings)\n"
            " 9.  Security (from Base Settings)\n"
            "10.  switch 1 provision (from Model)\n"
            "11.  ip domain name\n"
            "12.  SSH / Crypto (from Base Settings)\n"
            "13.  Switching Features (from Base Settings)\n"
            "14.  VLAN Definitions (from Profile)\n"
            "15.  Custom Sections - Before Interfaces\n"
            "16.  Disable ALL ports (Model port groups + Disabled Port "
            "Template)\n"
            "17.  VLAN 1 shutdown\n"
            "18.  Management Port (from Base Settings)\n"
            "19.  Port Assignments (Profile roles applied to interfaces)\n"
            "20.  Management VLAN interface (IP from wizard)\n"
            "21.  Default gateway\n"
            "22.  Custom Sections - After Interfaces\n"
            "23.  Line Configuration (from Base Settings)\n"
            "24.  Banner Login (from Base Settings)\n"
            "25.  end")

        # ---- Tips ----
        heading("Tips")
        body(
            "- All data is saved as JSON files in the data/ folder. You can "
            "back up or share these files with your team.\n\n"
            "- You can create multiple Site Profiles for different deployment "
            "types using the same Interface Roles and Switch Models.\n\n"
            "- If you need a port configured differently than the profile "
            "default, adjust it in the wizard's Step 2 - the changes only "
            "affect the current config, not the saved profile.\n\n"
            "- The Disabled Port Template runs on every port BEFORE your "
            "assignments, so any port you don't explicitly assign a role to "
            "will be shut down and placed on the blackhole VLAN.\n\n"
            "- Leave any Base Settings section blank to omit it entirely "
            "from the generated config.\n\n"
            "- The 'interface' keyword is added automatically. In port "
            "assignments, just enter the range text - e.g. "
            "'range GigabitEthernet1/0/1-12' (not 'interface range ...').")


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
        file_mb.configure(menu=file_menu)

        theme_mb = tk.Menubutton(self.menubar_frame, text="Theme", **menu_kw)
        theme_mb.pack(side="left")
        theme_menu = tk.Menu(theme_mb, **drop_kw)
        self._theme_var = tk.StringVar(value=self._current_theme_id())
        for tid, t in THEMES.items():
            theme_menu.add_radiobutton(
                label=t["name"], variable=self._theme_var, value=tid,
                command=lambda tid=tid: self._switch_theme(tid))
        theme_mb.configure(menu=theme_menu)

        # load data
        self.models   = load_json("models.json",        {})
        self.roles    = load_json("roles.json",          {})
        self.profiles = load_json("profiles.json",       {})
        self.base     = load_json("base_settings.json",  {})

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
            messagebox.showinfo("Exported",
                                f"Settings exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _import_settings(self):
        path = filedialog.askopenfilename(
            filetypes=[("ZIP Archive", "*.zip"), ("All", "*.*")])
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                valid = [n for n in names if n in self._SETTINGS_FILES]
                if not valid:
                    messagebox.showwarning(
                        "Invalid",
                        "The selected ZIP does not contain NetForge settings.")
                    return
                if not messagebox.askyesno(
                        "Import Settings",
                        f"This will overwrite your current settings:\n\n"
                        f"  {', '.join(valid)}\n\n"
                        "Continue?"):
                    return
                os.makedirs(DATA_DIR, exist_ok=True)
                for name in valid:
                    zf.extract(name, DATA_DIR)
        except zipfile.BadZipFile:
            messagebox.showerror("Import Error",
                                 "The selected file is not a valid ZIP.")
            return
        except Exception as exc:
            messagebox.showerror("Import Error", str(exc))
            return

        # reload data and refresh all tabs
        self.models   = load_json("models.json",       {})
        self.roles    = load_json("roles.json",         {})
        self.profiles = load_json("profiles.json",      {})
        self.base     = load_json("base_settings.json", {})
        self._rebuild_tabs()
        messagebox.showinfo("Imported",
                            "Settings imported successfully.\n"
                            "All tabs have been refreshed.")

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

    def _switch_theme(self, tid):
        if tid not in THEMES:
            return
        C.update(THEMES[tid])
        _save_theme(tid)
        apply_theme(self.root)
        # refresh custom menu bar colours
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
        self._rebuild_tabs()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
