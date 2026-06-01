"""Switch Models tab."""

import json

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
from netforge.ui.widgets import PanedWindow, ScrollFrame, _CheckList

class ModelsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.pg_rows = []
        self._build()

    def _build(self):
        paned = PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Switch Models",
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
        if self.show_hidden.get():
            names = list(self.app.models.keys())
        else:
            names = self.app.visible_keys("models")
        self.lb.populate(names)
        for n in names:
            if self.app.is_hidden("models", n):
                self.lb.set_dim(n, True)

    def _toggle_hide(self):
        _toggle_hidden_batch(self, "models", "model")

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


