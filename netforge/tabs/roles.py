"""Interface Roles tab."""

import json
import re

import tkinter as tk
from tkinter import ttk

from netforge.data.storage import save_json
from netforge.ui.helpers import (
    _ask,
    _attach_context_menu,
    _copy_name,
    _dialog,
    _field,
    _section,
    _toggle_hidden_batch,
)
from netforge.ui.theme import C
from netforge.ui.widgets import PanedWindow, ScrollFrame, _CheckList
from netforge.validate import _VAR_RE

class RolesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        paned = PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Interface Roles",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.show_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="Show hidden",
                        variable=self.show_hidden,
                        command=self._refresh
                        ).pack(anchor="w", padx=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="New",        command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Select All", command=self.lb.select_all).pack(side="left", padx=2)
        ttk.Button(bf, text="Hide",       command=self._toggle_hide).pack(side="left", padx=2)
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
                       "  inject {{ ip }} and {{ mask }} into the role template.\n"
                       "  If Step 3 leaves IP or Mask blank, the renderer falls back\n"
                       "  to the profile's Layer 3 -> Routed Interface fields, so a\n"
                       "  site-wide mask can live on the profile instead of Step 3."
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

        btns = ttk.Frame(form); btns.pack(fill="x", padx=5, pady=(10, 4))
        ttk.Button(btns, text="Save Role",
                   command=self._save).pack(side="left")
        ttk.Button(btns, text="Preview",
                   command=self._preview).pack(side="left", padx=6)

        _section(form, "Preview (sample values)")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Renders the template above with sample values: "
                       "{{ description }}, plus {{ ip }}/{{ mask }} when\n"
                       "  'Requires per-switch IP' is on. Any other variable "
                       "shows as a <name> placeholder so you can\n"
                       "  see where the Site Profile values land."
                  ).pack(anchor="w", padx=5, pady=(2, 2))
        self.preview = tk.Text(form, height=8, font=("Consolas", 10),
                               bg=C["bg_input"], fg=C["fg"],
                               insertbackground=C["fg"],
                               selectbackground=C["sel_bg"],
                               relief="flat", bd=2, wrap="word")
        self.preview.pack(fill="both", expand=True, padx=5, pady=(0, 8))
        self.preview.configure(state="disabled")
        _attach_context_menu(self.preview)
        self._refresh()

    def _preview(self):
        """Render the current template with sample/placeholder values."""
        from jinja2.sandbox import SandboxedEnvironment
        text = self.cmds.get("1.0", "end").rstrip("\n")
        ctx = {"description": "Example description"}
        if self.requires_ip.get():
            ctx["ip"] = "10.0.0.1"
            ctx["mask"] = "255.255.255.0"
        for var in set(_VAR_RE.findall(text)):
            ctx.setdefault(var, f"<{var}>")
        try:
            rendered = SandboxedEnvironment().from_string(text).render(**ctx)
        except Exception as exc:
            rendered = f"! render error: {exc}"
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", rendered)
        self.preview.configure(state="disabled")

    def _refresh(self):
        if self.show_hidden.get():
            names = list(self.app.roles.keys())
        else:
            names = self.app.visible_keys("roles")
        self.lb.populate(names)
        for n in names:
            if self.app.is_hidden("roles", n):
                self.lb.set_dim(n, True)

    def _toggle_hide(self):
        _toggle_hidden_batch(self, "roles", "role")

    def _on_select(self, name=None):
        if not name:
            return
        role = self.app.roles.get(name, {})
        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.cmds.delete("1.0", "end")
        self.cmds.insert("1.0", role.get("commands", ""))
        self.requires_ip.set(bool(role.get("requires_ip", False)))
        self._preview()

    def _new(self):
        self.lb.clear_selection()
        self.name_e.delete(0, "end")
        self.cmds.delete("1.0", "end")
        self.requires_ip.set(False)
        self._preview()

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


