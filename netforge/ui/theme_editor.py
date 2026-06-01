"""Custom theme editor dialog."""

import tkinter as tk
from tkinter import colorchooser, ttk

from netforge.data.storage import load_json, save_json
from netforge.ui.theme import C, THEMES, THEME_KEYS, apply_theme
from netforge.ui.win_theme import _apply_icon
from netforge.ui.helpers import _ask, _copy_name, _dialog

class _ThemeEditorDialog:
    """Modal dialog for creating and editing custom themes."""

    def __init__(self, app, on_close=None):
        self.app      = app
        self.on_close = on_close
        self._custom      = self._load_custom()   # tid -> theme dict
        self._selected_id = None
        self._color_vars  = {}   # key -> StringVar
        self._swatches    = {}   # key -> tk.Label (colored square)

        dlg = tk.Toplevel()
        self.dlg = dlg
        dlg.title("Custom Theme Editor")
        dlg.configure(bg=C["bg"])
        dlg.resizable(True, True)
        _apply_icon(dlg)
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




# ===================================================================
