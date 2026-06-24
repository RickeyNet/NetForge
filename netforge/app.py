"""NetForge application shell: App class and entry point."""

import json
import os
import sys
import ctypes
import tkinter as tk
import zipfile
from tkinter import filedialog, ttk

from netforge.data.base_settings import load_base_settings, resolve_base
from netforge.data.storage import (
    DATA_DIR,
    load_json,
    merge_bundled_data,
    save_json,
)
from netforge.tabs import (
    BaseTab,
    FtdTab,
    GenerateTab,
    GuideTab,
    ModelsTab,
    ProfilesTab,
    RolesTab,
)
from netforge.ui.helpers import _ask, _dialog
from netforge.ui.theme import (
    C,
    THEMES,
    _load_theme,
    _save_theme,
    apply_theme,
)
from netforge.ui.theme_editor import _ThemeEditorDialog
from netforge.ui.win_theme import _apply_icon

_RECENT_MAX = 10

merge_bundled_data()

# Apply saved theme preference
_load_theme()


class App:
    def __init__(self, root):
        self.root = root
        root.title("NetForge Config Generator")
        root.geometry("1050x780")
        root.minsize(900, 600)

        # Set the window / taskbar icon
        _apply_icon(root)

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

        help_mb = tk.Menubutton(self.menubar_frame, text="Help", **menu_kw)
        help_mb.pack(side="left")
        help_menu = tk.Menu(help_mb, **drop_kw)
        help_menu.add_command(label="Keyboard Shortcuts    F1",
                              command=lambda: self._sc_show_help())
        help_mb.configure(menu=help_menu)

        # Discoverability hint: small dimmed label on the right side of
        # the menubar so users see that F1 reveals shortcuts.
        tk.Label(self.menubar_frame,
                 text="Press F1 for shortcuts",
                 bg=C["bg2"], fg=C["border"],
                 font=("Segoe UI", 8)).pack(side="right", padx=8)

        # load data
        self.models   = load_json("models.json",        {})
        self.roles    = load_json("roles.json",          {})
        self.profiles = load_json("profiles.json",       {})
        self.base     = load_base_settings()
        self._migrate_profile_credentials()
        # Hidden item names per category: models, roles, profiles, base_sets.
        # Lets users clear bundled clutter from list/dropdown UIs without
        # deleting the underlying data.
        self._load_hidden()

        # tabs
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=5, pady=5)

        self.gen_tab = GenerateTab(self.nb, self)
        self.nb.add(self.gen_tab,  text="  Generate Config  ")

        self.models_tab   = ModelsTab(self.nb, self)
        self.roles_tab    = RolesTab(self.nb, self)
        self.profiles_tab = ProfilesTab(self.nb, self)
        self.base_tab     = BaseTab(self.nb, self)
        self.ftd_tab      = FtdTab(self.nb, self)
        self.nb.add(self.models_tab,   text="  Switch Models  ")
        self.nb.add(self.roles_tab,    text="  Interface Roles  ")
        self.nb.add(self.profiles_tab, text="  Site Profiles  ")
        self.nb.add(self.base_tab,     text="  Base Settings  ")
        self.nb.add(self.ftd_tab,      text="  FTD Setup  ")
        self.nb.add(GuideTab(self.nb, self), text="  How-To Guide  ")

        self._install_shortcuts()

    # ---- keyboard shortcuts ------------------------------------------
    # Tab order matches self.nb: 0=Generate, 1=Models, 2=Roles,
    # 3=Profiles, 4=Base, 5=FTD, 6=Guide.
    _SHORTCUTS = [
        ("Ctrl+1",       "Jump to Generate Config tab"),
        ("Ctrl+2",       "Jump to Switch Models tab"),
        ("Ctrl+3",       "Jump to Interface Roles tab"),
        ("Ctrl+4",       "Jump to Site Profiles tab"),
        ("Ctrl+5",       "Jump to Base Settings tab"),
        ("Ctrl+6",       "Jump to FTD Setup tab"),
        ("Ctrl+7",       "Jump to How-To Guide tab"),
        ("Ctrl+S",       "Save the active editor "
                         "(Model / Role / Profile / Base / Config)"),
        ("Ctrl+G",       "Generate config (switches to Generate tab first)"),
        ("Ctrl+Shift+C", "Copy generated config to clipboard"),
        ("Ctrl+Right",   "Wizard: advance to next step (Generate tab)"),
        ("Ctrl+Left",    "Wizard: go back one step (Generate tab)"),
        ("F1",           "Show this shortcut list"),
    ]

    def _install_shortcuts(self):
        r = self.root
        for i in range(7):
            r.bind_all(f"<Control-Key-{i+1}>",
                       lambda _e, idx=i: self._sc_select_tab(idx))
        r.bind_all("<Control-s>",      lambda _e: self._sc_save())
        r.bind_all("<Control-S>",      lambda _e: self._sc_save())
        r.bind_all("<Control-g>",      lambda _e: self._sc_generate())
        r.bind_all("<Control-G>",      lambda _e: self._sc_generate())
        r.bind_all("<Control-Shift-C>", lambda _e: self._sc_copy())
        r.bind_all("<Control-Right>",  lambda _e: self._sc_wizard_next())
        r.bind_all("<Control-Left>",   lambda _e: self._sc_wizard_back())
        r.bind_all("<F1>",             lambda _e: self._sc_show_help())

    def _sc_select_tab(self, idx):
        try:
            self.nb.select(idx)
        except tk.TclError:
            pass
        return "break"

    def _active_tab_widget(self):
        try:
            cur = self.nb.select()
            return self.root.nametowidget(cur) if cur else None
        except tk.TclError:
            return None

    def _sc_save(self):
        w = self._active_tab_widget()
        save = getattr(w, "_save", None)
        if callable(save):
            try:
                save()
            except Exception:
                pass
        return "break"

    def _sc_generate(self):
        gen = getattr(self, "gen_tab", None)
        if gen is None:
            return "break"
        try:
            self.nb.select(gen)
        except tk.TclError:
            pass
        fn = getattr(gen, "_generate", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        return "break"

    def _sc_copy(self):
        gen = getattr(self, "gen_tab", None)
        fn = getattr(gen, "_copy", None) if gen else None
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        return "break"

    def _sc_wizard_next(self):
        gen = getattr(self, "gen_tab", None)
        if gen is None or self._active_tab_widget() is not gen:
            return "break"
        step = getattr(gen, "current_step", 0)
        try:
            if step == 0:
                gen._step1_next()
            elif step == 1:
                gen._step2_next()
        except Exception:
            pass
        return "break"

    def _sc_wizard_back(self):
        gen = getattr(self, "gen_tab", None)
        if gen is None or self._active_tab_widget() is not gen:
            return "break"
        step = getattr(gen, "current_step", 0)
        try:
            if step == 2:
                gen._step3_back()
            elif step == 1:
                gen._show_step(0)
        except Exception:
            pass
        return "break"

    def _sc_show_help(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Keyboard Shortcuts")
        dlg.configure(bg=C["bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        _apply_icon(dlg)
        dlg.grab_set()
        tk.Frame(dlg, bg=C["accent"], height=3).pack(fill="x")
        inner = ttk.Frame(dlg, padding=(22, 14, 22, 18))
        inner.pack()
        ttk.Label(inner, text="Keyboard Shortcuts",
                  style="Sec.TLabel").pack(anchor="w")
        grid = ttk.Frame(inner)
        grid.pack(anchor="w", pady=(8, 14))
        for row, (key, desc) in enumerate(self._SHORTCUTS):
            ttk.Label(grid, text=key, font=("Consolas", 10)
                      ).grid(row=row, column=0, sticky="w", padx=(0, 18))
            ttk.Label(grid, text=desc
                      ).grid(row=row, column=1, sticky="w")
        ttk.Button(inner, text="OK",
                   command=dlg.destroy).pack(anchor="e")
        dlg.update_idletasks()
        try:
            rx = self.root.winfo_x() + (self.root.winfo_width()
                                        - dlg.winfo_width()) // 2
            ry = self.root.winfo_y() + (self.root.winfo_height()
                                        - dlg.winfo_height()) // 2
            dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
        except Exception:
            pass
        return "break"

    # ---- export / import settings ----
    _SETTINGS_FILES = [
        "models.json", "roles.json", "profiles.json", "base_settings.json",
        "theme.json",
    ]

    def _export_settings(self):
        if not _ask(
                "Export Settings",
                "This ZIP will contain your profiles and base settings "
                "in plain text, including any credentials you've entered "
                "(enable secrets, local user passwords, SNMP communities, "
                "NTP/BGP keys).\n\n"
                "Store and share it accordingly. Continue?"):
            return
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
                # Do not trust zf.extract() with archive-supplied paths
                # (Zip Slip). Read each member and write it ourselves to a
                # path built from a known-good basename inside DATA_DIR.
                for name in valid:
                    dest = os.path.join(DATA_DIR, os.path.basename(name))
                    if os.path.dirname(
                            os.path.realpath(dest)) != os.path.realpath(
                            DATA_DIR):
                        continue
                    data = zf.read(name)
                    try:
                        json.loads(data.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        _dialog(
                            "Import Error",
                            f"'{name}' is not valid JSON; skipped.",
                            "error")
                        continue
                    with open(dest, "wb") as out:
                        out.write(data)
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
        self._migrate_profile_credentials()
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

    # ---- profile credential migration --------------------------------
    def _migrate_profile_credentials(self):
        """Convert legacy credentials.local_username/admin_password into
        the new credentials.users list shape. Writes profiles.json only
        if at least one profile actually changed.
        """
        changed = False
        for prof in self.profiles.values():
            creds = prof.get("credentials")
            if not isinstance(creds, dict):
                continue
            if creds.get("users"):
                continue
            legacy_name = creds.get("local_username")
            legacy_pw   = creds.get("admin_password")
            if not (legacy_name or legacy_pw):
                continue
            creds["users"] = [{
                "name": legacy_name or "",
                "password": legacy_pw or "",
                "privilege": 15,
            }]
            creds.pop("local_username", None)
            creds.pop("admin_password", None)
            changed = True
        if changed:
            save_json("profiles.json", self.profiles)

    # ---- hidden-items state ------------------------------------------
    _HIDDEN_CATEGORIES = ("models", "roles", "profiles", "base_sets")

    def _load_hidden(self):
        raw = load_json("hidden.json", {}) or {}
        self.hidden = {cat: set(raw.get(cat, []) or [])
                       for cat in self._HIDDEN_CATEGORIES}

    def _save_hidden(self):
        save_json("hidden.json",
                  {cat: sorted(self.hidden[cat])
                   for cat in self._HIDDEN_CATEGORIES})

    def _all_keys(self, category):
        if category == "models":
            return list(self.models.keys())
        if category == "roles":
            return list(self.roles.keys())
        if category == "profiles":
            return list(self.profiles.keys())
        if category == "base_sets":
            return list((self.base or {}).get("sets", {}).keys())
        return []

    def is_hidden(self, category, name):
        return name in self.hidden.get(category, set())

    def toggle_hidden(self, category, name):
        """Flip the hidden flag for *name*. Returns the new state (bool)."""
        s = self.hidden.setdefault(category, set())
        if name in s:
            s.discard(name)
            new_state = False
        else:
            s.add(name)
            new_state = True
        self._save_hidden()
        return new_state

    def visible_keys(self, category):
        """Names in this category that are not hidden, preserving order."""
        hidden = self.hidden.get(category, set())
        return [n for n in self._all_keys(category) if n not in hidden]

    def _visible_base_set_names(self):
        """Sorted base-set names with hidden ones filtered out."""
        hidden = self.hidden.get("base_sets", set())
        return [n for n in self.base_set_names() if n not in hidden]

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
        self.ftd_tab      = FtdTab(self.nb, self)

        self.nb.add(self.gen_tab,      text="  Generate Config  ")
        self.nb.add(self.models_tab,   text="  Switch Models  ")
        self.nb.add(self.roles_tab,    text="  Interface Roles  ")
        self.nb.add(self.profiles_tab, text="  Site Profiles  ")
        self.nb.add(self.base_tab,     text="  Base Settings  ")
        self.nb.add(self.ftd_tab,      text="  FTD Setup  ")
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


def _set_windows_app_id():
    """Set an explicit AppUserModelID so the Windows taskbar shows our icon
    instead of grouping us under the Python interpreter."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "NetForge.NetForge.App.1"
        )
    except Exception:
        pass


def main():
    _set_windows_app_id()
    root = tk.Tk()
    App(root)
    root.mainloop()
