"""Base Settings tab."""

import json

import tkinter as tk
from tkinter import ttk

from netforge.data.storage import save_json
from netforge.ui.helpers import (
    _ask,
    _attach_context_menu,
    _autosize_textarea,
    _copy_name,
    _dialog,
    _field,
    _section,
    _textarea,
    _toggle_hidden_batch,
)
from netforge.ui.theme import C
from netforge.ui.widgets import PanedWindow, ScrollFrame, _CheckList
from netforge.validate import _VAR_RE

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
        paned = PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list of base sets --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Base Settings",
                  style="Sec.TLabel").pack(anchor="w", padx=4, pady=4)
        self.show_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="Show hidden",
                        variable=self.show_hidden,
                        command=self._refresh
                        ).pack(anchor="w", padx=4)
        self.lb = _CheckList(left, on_click=self._on_select)
        self.lb.pack(fill="both", expand=True, padx=4, pady=4)
        bf = ttk.Frame(left); bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="+ Add",      command=self._new).pack(side="left", padx=2)
        ttk.Button(bf, text="Duplicate",  command=self._duplicate).pack(side="left", padx=2)
        ttk.Button(bf, text="Set Default", command=self._set_default).pack(side="left", padx=2)
        ttk.Button(bf, text="Hide",       command=self._toggle_hide).pack(side="left", padx=2)
        ttk.Button(bf, text="Delete",     command=self._delete,
                   style="Del.TButton").pack(side="left", padx=2)

        # -- right: editor --
        # Wrapper holds a sticky search bar (top), the scrolling form
        # (middle), and a sticky Save footer (bottom), so search and Save
        # both stay visible as the form grows and pushes content
        # off-screen.
        right_wrap = ttk.Frame(paned); paned.add(right_wrap, weight=1)

        search_bar = ttk.Frame(right_wrap)
        search_bar.pack(side="top", fill="x")
        ttk.Label(search_bar, text="Search:").pack(side="left",
                                                   padx=(5, 4), pady=6)
        self.search_e = ttk.Entry(search_bar)
        self.search_e.pack(side="left", fill="x", expand=True, pady=6)
        _attach_context_menu(self.search_e)
        self.search_e.bind("<Return>", lambda _e: self._do_search())
        self.search_e.bind("<KP_Enter>", lambda _e: self._do_search())
        ttk.Button(search_bar, text="Find",
                   command=self._do_search).pack(side="left", padx=4, pady=6)
        ttk.Button(search_bar, text="Clear",
                   command=self._clear_search).pack(side="left",
                                                    padx=(0, 5), pady=6)
        self.search_status = ttk.Label(search_bar, text="",
                                       style="Hint.TLabel")
        self.search_status.pack(side="left", padx=4, pady=6)
        ttk.Separator(right_wrap, orient="horizontal").pack(side="top",
                                                            fill="x")

        footer = ttk.Frame(right_wrap)
        footer.pack(side="bottom", fill="x")
        ttk.Separator(footer, orient="horizontal").pack(fill="x")
        ttk.Button(footer, text="Save Base Settings",
                   command=self._save).pack(padx=5, pady=8, anchor="w")
        right = ScrollFrame(right_wrap); right.pack(fill="both", expand=True)
        self._scroll = right
        form = right.inner
        # Map text-area key -> human title, for search result reporting.
        self._section_titles = {}

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
                  "{{ profile }}, {{ work_order }}, {{ date }}",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.fields["filename_template"] = _field(
            form, "Filename Template",
            "{{ hostname }}_{{ model }}_{{ profile }}")

        # Sections mirror the categories in the Cisco 9300 L3 Switch
        # Baseline spreadsheet. Internal keys are stable slugs; titles match
        # the spreadsheet headers so users can paste each block straight
        # from the workbook.
        sections = [
            ("basic_config",       "Basic Configuration",
             "hostname, domain, login block, spanning-tree mode, "
             "errdisable, udld, file privilege, etc."),
            ("services_functions", "Services and Functions Config",
             "no service config / finger / pad / call-home, "
             "service password-encryption, service timestamps, no cdp run"),
            ("ip_services",        "IP Services",
             "ip routing, no ip boot/bootp/dns/finger/rcmd, "
             "no ip gratuitous-arps, ip icmp rate-limit, ip options block"),
            ("snooping",           "Snooping",
             "ip igmp snooping, ip dhcp snooping, "
             "ip dhcp snooping vlan <ids>"),
            ("http_server",        "HTTP Server",
             "no ip http server / secure-server, "
             "ip http timeout-policy"),
            ("mgmt_vrf",           "Management VRF",
             "vrf definition Mgmt-vrf block (if needed)"),
            ("aaa_radius",         "AAA Password Policy / RADIUS / Local Account",
             "aaa new-model, password policy, radius servers, "
             "aaa authentication / authorization, local admin user"),
            ("ssh",                "SSH Config",
             "crypto key generate, ip ssh version/time-out, "
             "ssh server algorithm encryption / mac"),
            ("logging",            "Logging",
             "no logging console, logging host, "
             "logging buffered, logging trap"),
            ("archive",            "Archive Config",
             "archive / log config / logging enable / "
             "notify syslog contenttype / hidekeys"),
            ("vty_config",         "VTY Config",
             "line con 0, line vty 0 4 / 5 15, "
             "exec-timeout, transport input ssh"),
            ("misc",               "Miscellaneous Configs",
             "no ip source-route, switching features "
             "(VTP, redundancy, transceiver monitoring), "
             "any remaining one-off commands"),
        ]
        for key, title, hint in sections:
            _section(form, title)
            ttk.Label(form, text=f"  {hint}",
                      style="Hint.TLabel").pack(anchor="w", padx=5)
            self.text_areas[key] = _autosize_textarea(
                _textarea(form, "", "", h=2), min_h=2, max_h=40)
            self._section_titles[key] = title

        _section(form, "Banner LOGIN")
        ttk.Label(form, text="  Enter the banner text only - the app adds "
                  "the 'banner login ^' wrapper.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["banner"] = _autosize_textarea(
            _textarea(form, "", "", h=2), min_h=2, max_h=40)
        self._section_titles["banner"] = "Banner LOGIN"

        _section(form, "Disabled Port Template")
        ttk.Label(form, text="  Commands applied to every port during the "
                  "'disable all' step.\n"
                  "  Use {{ blackhole_vlan }} or any profile variable.",
                  style="Hint.TLabel").pack(anchor="w", padx=5)
        self.text_areas["disabled_port_template"] = _autosize_textarea(
            _textarea(form, "", "", h=2), min_h=2, max_h=40)
        self._section_titles["disabled_port_template"] = "Disabled Port Template"

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

        self._refresh()

    # -- search ------------------------------------------------------------
    _SEARCH_TAG = "search_match"

    def _all_search_targets(self):
        """Yield (label, widget) pairs covering every text area, custom
        config section commands box, and the filename template entry."""
        for key, title in self._section_titles.items():
            w = self.text_areas.get(key)
            if w is not None:
                yield (title, w)
        ft = self.fields.get("filename_template")
        if ft is not None:
            yield ("Filename Template", ft)
        for row in self.cs_rows:
            name = (row["name"].get() or "").strip() or "(unnamed)"
            yield (f"Custom Section: {name}", row["commands"])

    def _clear_search(self):
        for _label, w in self._all_search_targets():
            if isinstance(w, tk.Text):
                try:
                    w.tag_remove(self._SEARCH_TAG, "1.0", "end")
                except tk.TclError:
                    pass
        self.search_status.configure(text="")

    def _do_search(self):
        needle = self.search_e.get()
        self._clear_search()
        if not needle.strip():
            return
        needle_low = needle.lower()
        per_section = []   # list of (label, count, widget, first_index)
        for label, w in self._all_search_targets():
            if isinstance(w, tk.Text):
                w.tag_configure(self._SEARCH_TAG,
                                background="#ffd866", foreground="#000000")
                count = 0
                first_idx = None
                start = "1.0"
                while True:
                    idx = w.search(needle, start, nocase=True, stopindex="end")
                    if not idx:
                        break
                    end_idx = f"{idx}+{len(needle)}c"
                    w.tag_add(self._SEARCH_TAG, idx, end_idx)
                    if first_idx is None:
                        first_idx = idx
                    count += 1
                    start = end_idx
                if count:
                    per_section.append((label, count, w, first_idx))
            else:
                val = (w.get() or "")
                if needle_low in val.lower():
                    per_section.append((label, 1, w, None))

        if not per_section:
            self.search_status.configure(text="No matches.")
            return

        label0, _c0, widget0, first_idx0 = per_section[0]
        self._scroll_widget_into_view(widget0)
        if isinstance(widget0, tk.Text) and first_idx0:
            try:
                widget0.see(first_idx0)
            except tk.TclError:
                pass

        total = sum(c for _l, c, _w, _i in per_section)
        if len(per_section) == 1:
            summary = f"{total} match in {per_section[0][0]}"
        else:
            tops = ", ".join(f"{name} ({c})" for name, c, _w, _i in per_section[:3])
            more = "" if len(per_section) <= 3 else f", +{len(per_section)-3} more"
            summary = f"{total} matches: {tops}{more}"
        self.search_status.configure(text=summary)

    def _scroll_widget_into_view(self, widget):
        scroll = getattr(self, "_scroll", None)
        if scroll is None:
            return
        canvas = scroll.canvas
        canvas.update_idletasks()
        try:
            y = widget.winfo_y()
            parent = widget.master
            inner = scroll.inner
            while parent is not None and parent is not inner:
                y += parent.winfo_y()
                parent = parent.master
            total = max(1, inner.winfo_height())
            frac = max(0.0, min(1.0, (y - 20) / total))
            canvas.yview_moveto(frac)
        except tk.TclError:
            pass

    # -- list helpers --
    def _refresh(self):
        all_names = self.app.base_set_names()
        if self.show_hidden.get():
            names = all_names
        else:
            hidden = self.app.hidden.get("base_sets", set())
            names = [n for n in all_names if n not in hidden]
        self.lb.populate(names)
        for n in names:
            if self.app.is_hidden("base_sets", n):
                self.lb.set_dim(n, True)

    def _toggle_hide(self):
        _toggle_hidden_batch(self, "base_sets", "base set")

    def _on_select(self, name=None):
        if not name:
            return
        b = (self.app.base or {}).get("sets", {}).get(name, {}) or {}

        # Clear any stale search highlights when switching sets.
        self._clear_search()

        self.name_e.delete(0, "end"); self.name_e.insert(0, name)
        self.default_var.set(name == (self.app.base or {}).get("default"))

        for key, widget in self.fields.items():
            widget.delete(0, "end")
            widget.insert(0, b.get(key, ""))
        for key, widget in self.text_areas.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", b.get(key, ""))
            if hasattr(widget, "_autosize"):
                widget._autosize()

        self._clear_cs()
        for cs in b.get("custom_sections", []) or []:
            self._add_cs(cs)
        # The textareas above autosize asynchronously via <<Modified>> and
        # after_idle; their final heights propagate to the inner frame's
        # reqheight only after idle.  Sync the scrollregion once more after
        # that settles so the scrollbar tracks the real content, not any
        # leftover slack from the previously selected base set.
        self.after_idle(self._scroll.sync_scrollregion)

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

        cmds = tk.Text(frame, height=2, font=("Consolas", 9),
                       bg=C["bg_input"], fg=C["fg"],
                       insertbackground=C["fg"],
                       selectbackground=C["sel_bg"],
                       relief="flat", bd=2, wrap="word")
        cmds.pack(fill="x", pady=(4, 0))
        _attach_context_menu(cmds)
        _autosize_textarea(cmds, min_h=2, max_h=20)

        row = {"frame": frame, "name": name_e,
               "position": pos_cb, "commands": cmds}

        prev_bar = ttk.Frame(frame); prev_bar.pack(fill="x", pady=(4, 0))
        ttk.Button(prev_bar, text="Preview",
                   command=lambda r=row: self._preview_cs(r)).pack(side="left")
        ttk.Label(prev_bar,
                  text="  Rendered with <name> placeholders for the Site "
                       "Profile's role variables.",
                  style="Hint.TLabel").pack(side="left", padx=6)
        prev = tk.Text(frame, height=2, font=("Consolas", 9),
                       bg=C["bg_input"], fg=C["fg"],
                       insertbackground=C["fg"],
                       selectbackground=C["sel_bg"],
                       relief="flat", bd=2, wrap="word")
        prev.pack(fill="x", pady=(2, 0))
        prev.configure(state="disabled")
        _attach_context_menu(prev)
        row["preview"] = prev

        if isinstance(data, dict):
            name_e.insert(0, data.get("name", ""))
            pos = data.get("position", "post-interface")
            pos_cb.set("Before Interfaces"
                       if pos == "pre-interface" else "After Interfaces")
            cmds.insert("1.0", data.get("commands", ""))
            if hasattr(cmds, "_autosize"):
                cmds._autosize()
            self._preview_cs(row)

        self.cs_rows.append(row)
        self.after_idle(self._scroll.sync_scrollregion)

    def _preview_cs(self, row):
        """Render a custom section with <name> placeholders for variables."""
        from jinja2.sandbox import SandboxedEnvironment
        text = row["commands"].get("1.0", "end").rstrip("\n")
        ctx = {var: f"<{var}>" for var in set(_VAR_RE.findall(text))}
        try:
            rendered = SandboxedEnvironment().from_string(text).render(**ctx)
        except Exception as exc:
            rendered = f"! render error: {exc}"
        w = row["preview"]
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", rendered)
        w.configure(state="disabled")

    def _del_cs(self, frame):
        self.cs_rows = [r for r in self.cs_rows if r["frame"] is not frame]
        frame.destroy()
        self.after_idle(self._scroll.sync_scrollregion)

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


