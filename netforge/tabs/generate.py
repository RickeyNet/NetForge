"""Generate Config wizard tab."""

import re

import tkinter as tk
from tkinter import filedialog, ttk

from netforge.data.base_settings import resolve_base
from netforge.data.iface import expand_port_groups_for_stack, expand_range_iface
from netforge.render import _normalize_l3_sections, _vlan_id_remap, render_config_sections
from netforge.render.l3 import _find_routed_mgmt_entry, _profile_has_ospf
from netforge.serial_push import _SerialPushDialog
from netforge.ui.filename_template import apply_filename_template as _apply_filename_template
from netforge.ui.helpers import (
    _attach_context_menu,
    _autosize_textarea,
    _combo,
    _dialog,
    _field,
    _scrolled_text,
    _section,
)
from netforge.ui.l3_grid import (
    L3EntryGrid,
    _L3_KINDS,
    _L3_UI_ALIAS,
    _collect_l3_sw_from_grids,
    _site_routed_mgmt_override,
)
from netforge.ui.theme import C
from netforge.ui.widgets import PanedWindow, ScrollFrame

class GenerateTab(ttk.Frame):
    """Three-step wizard: Model & Site -> Port Assignments -> Switch Details."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_step = 0
        self.pa_rows = []          # port-assignment rows in step 2
        self._sections = {}        # populated after each generate
        self.l3_ip_rows = []       # routed-interface IP rows in step 3
        self.l3_gen_grids = {}
        self.l3_static_rows = []   # static-route rows in step 3
        self._last_synced_gateway = ""  # tracks auto-fill source for BGP fields
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
                               self.app.visible_keys("models"))
        self.profile_cb = _combo(center, "Site Profile",
                                 self.app.visible_keys("profiles"))

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
        ttk.Button(nav, text="Push to Switch...",
                   command=self._push).pack(side="left", padx=4)

        paned = PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        self._step3_paned = paned

        # -- left: form --
        left = ScrollFrame(paned)
        paned.add(left, weight=3)
        form = left.inner

        ttk.Label(form, text="Step 3 - Enter Per-Switch Details",
                  style="Sec.TLabel").pack(anchor="w", padx=5, pady=(5, 10))

        self.hostname    = _field(form, "Hostname")
        self.secret      = _field(form, "Enable Secret")

        # Local Users - editable copy of the profile's users list. Each row
        # renders as one `username NAME privilege P secret PW` line.
        users_lf = ttk.LabelFrame(form, text="Local Users", padding=5)
        users_lf.pack(fill="x", padx=5, pady=4)
        u_hint = ttk.Frame(users_lf); u_hint.pack(fill="x", pady=(0, 4))
        ttk.Label(u_hint, style="Hint.TLabel",
                  text="  Seeded from the selected profile. Edits stay local\n"
                       "  to this switch and don't write back to the profile."
                  ).pack(side="left", anchor="w", padx=2)
        ttk.Button(u_hint, text="+ Add User",
                   command=self._add_sw_user
                   ).pack(side="right", anchor="ne", padx=(6, 1))
        uh = ttk.Frame(users_lf); uh.pack(fill="x")
        uh.columnconfigure(0, weight=2, uniform="swusr")
        uh.columnconfigure(1, weight=2, uniform="swusr")
        uh.columnconfigure(2, weight=1, uniform="swusr")
        ttk.Label(uh, text="Username", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(uh, text="Password", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(uh, text="Privilege", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Frame(uh, width=30).grid(row=0, column=3, padx=(6, 1))
        self.sw_user_frame = ttk.Frame(users_lf)
        self.sw_user_frame.pack(fill="x")
        self.sw_user_rows = []

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

        # Per-switch VLAN overrides - shown only when the selected profile
        # has `allow_per_switch_vlans` enabled. The text replaces the
        # profile's VLAN definitions for this switch only.
        self.vlans_frame = ttk.Frame(form)
        _section(self.vlans_frame, "VLAN Definitions (this switch)")
        ttk.Label(self.vlans_frame, style="Hint.TLabel",
                  text="Edits apply to this switch only and replace the\n"
                       "profile's VLAN block at render time. For L3 profiles,\n"
                       "interface-Vlan blocks here move to L3 Interfaces;\n"
                       "edit SVI VLAN IDs in the SVIs section below."
                  ).pack(anchor="w", padx=5, pady=(2, 2))
        self.sw_vlans_text = tk.Text(
            self.vlans_frame, height=8, font=("Consolas", 9),
            bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2, wrap="word")
        self.sw_vlans_text.pack(fill="x", padx=5, pady=4)
        _attach_context_menu(self.sw_vlans_text)
        _autosize_textarea(self.sw_vlans_text, min_h=4, max_h=40)

        # Layer 3 Details (only shown when the selected profile is L3)
        self.l3_frame = ttk.Frame(form)
        _section(self.l3_frame, "Layer 3 Details")
        ttk.Label(self.l3_frame,
                  text="Per-switch L3 values. SVIs and OSPF come\n"
                       "from the profile.",
                  style="Hint.TLabel").pack(anchor="w", padx=5, pady=(2, 4))

        for kind in ("loopback", "routed_mgmt", "mgmt_svi"):
            grid = L3EntryGrid(kind, mode="generate").build_generate(self.l3_frame)
            self.l3_gen_grids[kind] = grid
            alias = _L3_UI_ALIAS[kind]
            setattr(self, f"{alias}_lf", grid.lf)
            setattr(self, f"{alias}_frame", grid.row_frame)
            setattr(self, f"{alias}_rows", grid.rows)
            if kind == "mgmt_svi":
                self.msvi_hint = grid.hint

        # Router ID (defaults to first loopback IP if blank). Shown only when
        # the profile has OSPF enabled.
        self.rid_lf = ttk.LabelFrame(self.l3_frame, text="OSPF Router ID",
                                     padding=5)
        self.rid_lf.pack(fill="x", padx=5, pady=4)
        self.router_id = _field(self.rid_lf, "Router ID")
        ttk.Label(self.rid_lf, style="Hint.TLabel",
                  text="  Leave blank to default to the first loopback IP."
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
        self.svi_ip_hint = ttk.Label(self.svi_ip_lf, style="Hint.TLabel",
                  text="  One row per SVI defined in the profile. IP /\n"
                       "  Mask pre-fill from the profile when set;\n"
                       "  override here for per-switch values."
                  )
        self.svi_ip_hint.pack(anchor="w", padx=2, pady=(0, 4))
        sih = ttk.Frame(self.svi_ip_lf); sih.pack(fill="x")
        sih.columnconfigure(0, weight=2, uniform="sviip")
        sih.columnconfigure(1, weight=2, uniform="sviip")
        sih.columnconfigure(2, weight=1, uniform="sviip")
        sih.columnconfigure(3, weight=1, uniform="sviip")
        self.svi_ip_hdr_vlan = ttk.Label(sih, text="VLAN", anchor="w")
        self.svi_ip_hdr_vlan.grid(row=0, column=0, sticky="ew", padx=1)
        self.svi_ip_hdr_desc = ttk.Label(sih, text="Description", anchor="w")
        self.svi_ip_hdr_desc.grid(row=0, column=1, sticky="ew", padx=1)
        ttk.Label(sih, text="IP", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Label(sih, text="Mask", anchor="w").grid(
            row=0, column=3, sticky="ew", padx=1)
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
        # Re-render preview and sync BGP ISP/peer fields when the Default
        # Gateway changes (one-way: BGP edits never change Default Gateway).
        self.gateway.bind("<KeyRelease>", self._on_gateway_changed, add="+")

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

        self.preview = _scrolled_text(
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
        self.after_idle(self._apply_step3_sash)

    def _apply_step3_sash(self):
        if self._step3_sash_set:
            return
        try:
            w = self._step3_paned.winfo_width()
            if w > 100:
                self._step3_paned.sashpos(0, w // 2)
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
        enable_val = creds.get("enable_secret", "")
        if enable_val:
            self.secret.delete(0, "end")
            self.secret.insert(0, enable_val)
        # Seed the per-switch users grid from the profile. Migrate the
        # legacy single-credential shape on the fly if no list is present.
        users = list(creds.get("users") or [])
        if not users:
            legacy_name = creds.get("local_username", "")
            legacy_pw   = creds.get("admin_password", "")
            if legacy_name or legacy_pw:
                users = [{"name": legacy_name, "password": legacy_pw,
                          "privilege": 15}]
        self._clear_sw_users()
        for u in users:
            self._add_sw_user(u)
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
        # Per-switch VLAN override visibility + seed from profile.
        if profile.get("allow_per_switch_vlans"):
            self.vlans_frame.pack(fill="x", padx=5, pady=2)
            self.sw_vlans_text.delete("1.0", "end")
            self.sw_vlans_text.insert("1.0",
                                      profile.get("vlan_definitions", "") or "")
            if hasattr(self.sw_vlans_text, "_autosize"):
                self.sw_vlans_text._autosize()
        else:
            self.vlans_frame.pack_forget()
            self.sw_vlans_text.delete("1.0", "end")
        self._show_step(1)

    def _populate_step2(self, model_name, profile_name):
        model   = self.app.models[model_name]
        profile = self.app.profiles[profile_name]

        # expand port groups for stack members
        stack = model.get("stack_members", 1)
        all_pgs = expand_port_groups_for_stack(
            model.get("port_groups", []), stack)

        # update reference label - group similar port types onto one line
        # e.g. GigabitEthernet1/0/1-24 .. GigabitEthernet4/0/1-24
        #   -> GigabitEthernet[1-4]/0/1 - 24
        groups = {}  # (name_part, tail, start, end) -> [member_nums]
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
                            values=["unassigned"] + self.app.visible_keys("roles"))
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
        self.model_cb["values"]   = self.app.visible_keys("models")
        self.profile_cb["values"] = self.app.visible_keys("profiles")

    def _apply_l3_visibility(self, profile):
        """Show/hide the Layer 3 Details frame and its sub-sections
        based on the profile's layer3 flag, the three l3_sections
        enable flags (loopback / routed_mgmt / mgmt_svi), and
        ospf.enabled. Pre-fills each section's IP / Mask from the
        profile when the per-switch field is blank. Default Gateway is
        always editable - it's required on every device."""
        layer3 = bool(profile.get("layer3", False))
        sections = _normalize_l3_sections(profile) if layer3 else {}
        ospf_enabled = _profile_has_ospf(profile)

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
            for grid in self.l3_gen_grids.values():
                grid.clear()
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

        allow_sw_vlans = bool(profile.get("allow_per_switch_vlans"))
        for kind, grid in self.l3_gen_grids.items():
            sec = sections.get(kind, {})
            if sec.get("enabled") and sec.get("entries"):
                if kind == "mgmt_svi":
                    if allow_sw_vlans:
                        grid.hint.configure(
                            text="  Per-switch management VLAN overrides. VLAN "
                                 "IDs can differ from the profile when needed."
                        )
                    else:
                        grid.hint.configure(
                            text=_L3_KINDS[kind]["generate"]["hint"]
                        )
                grid.lf.pack(fill="x", padx=5, pady=4)
                grid.populate(
                    sec.get("entries") or [],
                    editable_key=(allow_sw_vlans and kind == "mgmt_svi"),
                )
            else:
                grid.clear()

        # Router ID only relevant when OSPF is enabled in the profile.
        if ospf_enabled:
            self.rid_lf.pack(fill="x", padx=5, pady=4)

        # Routed Interface IPs only when at least one Step 2 port is
        # assigned to a role with requires_ip=True. Populate first so we
        # can read the row count, then decide whether to show the section.
        self._populate_l3_ip_rows()
        if self.l3_ip_rows:
            self.l3_ip_lf.pack(fill="x", padx=5, pady=4)

        # SVI section when the profile defines SVIs. With per-switch VLAN
        # overrides enabled, VLAN ID and Description become editable so
        # SVIs stay in sync with the VLAN block above.
        if profile.get("svis"):
            if allow_sw_vlans:
                self.svi_ip_lf.configure(text="SVIs (this switch)")
                self.svi_ip_hint.configure(
                    text="  Per-switch SVI definitions. VLAN IDs can differ\n"
                         "  from the profile so they stay in sync with the\n"
                         "  VLAN block above. IP / Mask override profile defaults."
                )
                self.svi_ip_hdr_vlan.configure(text="VLAN ID")
                self.svi_ip_hdr_desc.grid()
            else:
                self.svi_ip_lf.configure(text="SVI IPs")
                self.svi_ip_hint.configure(
                    text="  One row per SVI defined in the profile. IP,\n"
                         "  Mask, and Description can be overridden here\n"
                         "  for per-switch values."
                )
                self.svi_ip_hdr_vlan.configure(text="VLAN")
                self.svi_ip_hdr_desc.grid()
            self.svi_ip_lf.pack(fill="x", padx=5, pady=4)
            self._populate_svi_ip_rows(profile, editable=allow_sw_vlans)
        else:
            self._clear_svi_ip_rows()

        self.l3_static_lf.pack(fill="x", padx=5, pady=4)

        bgp_instances = (profile.get("bgp") or {}).get("instances") or []
        if bgp_instances:
            self.bgp_lf.pack(fill="x", padx=5, pady=4)
            self._populate_bgp_inst_blocks(bgp_instances)
            self._sync_gateway_to_bgp()
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
        the profile's Layer 3 -> Routed Interface section when the user
        hasn't typed one for that interface yet."""
        existing = {r["iface_name"]: (r["ip"].get(), r["mask"].get())
                    for r in self.l3_ip_rows}
        self._clear_l3_ip_rows()
        pn = self.profile_cb.get()
        profile = self.app.profiles.get(pn, {}) or {}
        rm_block = (_normalize_l3_sections(profile).get("routed_mgmt", {})
                    if profile.get("layer3") else {})
        rm_entries = rm_block.get("entries") or []
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
            rm_entry = _find_routed_mgmt_entry(iface, rm_entries)
            if not ip.get() and (rm_entry.get("ip") or "").strip():
                ip.insert(0, rm_entry.get("ip"))
            if not mask.get() and (rm_entry.get("mask") or "").strip():
                mask.insert(0, rm_entry.get("mask"))
            default_mask = ""
            if rm_entries:
                default_mask = (rm_entries[0].get("mask") or "").strip()
            if not mask.get() and default_mask:
                mask.insert(0, default_mask)
            self.l3_ip_rows.append({"frame": row, "iface_name": iface,
                                    "ip": ip, "mask": mask})

    def _clear_svi_ip_rows(self):
        for r in self.svi_ip_rows:
            r["frame"].destroy()
        self.svi_ip_rows.clear()

    def _populate_svi_ip_rows(self, profile, editable=False):
        """One row per SVI defined in the profile. Preserves any IPs
        the user already typed for the same VLAN. Pre-fills IP / Mask
        from profile.svis[].ip / .mask when the user hasn't typed a
        per-switch value yet (typical workflow: profile sets the mask
        site-wide, optionally a default IP).

        When *editable* is True (per-switch VLAN overrides enabled),
        VLAN ID is an editable Entry field and the full row is stored in
        sw['svis'] at render time. Description is always editable."""
        existing = {}
        for idx, r in enumerate(self.svi_ip_rows):
            if r.get("editable"):
                existing[idx] = {
                    "vlan": r["vlan"].get().strip(),
                    "desc": r["desc"].get().strip() if r.get("desc") else "",
                    "ip": r["ip"].get(),
                    "mask": r["mask"].get(),
                    "helpers": r.get("helpers", ""),
                }
            else:
                existing[idx] = {
                    "vlan": r["vlan"],
                    "desc": r["desc"].get().strip() if r.get("desc") else "",
                    "ip": r["ip"].get(),
                    "mask": r["mask"].get(),
                    "helpers": r.get("helpers", ""),
                }
        self._clear_svi_ip_rows()
        for idx, svi in enumerate(profile.get("svis", []) or []):
            vlan = (svi.get("vlan") or "").strip()
            if not vlan:
                continue
            desc = (svi.get("description") or "").strip()
            default_ip = (svi.get("ip") or "").strip()
            default_mask = (svi.get("mask") or "").strip()
            helpers_raw = svi.get("helper_addresses") or ""
            if isinstance(helpers_raw, list):
                helpers = ", ".join(str(h) for h in helpers_raw if str(h).strip())
            else:
                helpers = str(helpers_raw or "").strip()
            saved = existing.get(idx, {})
            row = ttk.Frame(self.svi_ip_frame); row.pack(fill="x", pady=1)
            row.columnconfigure(0, weight=2, uniform="sviip")
            row.columnconfigure(1, weight=2, uniform="sviip")
            row.columnconfigure(2, weight=1, uniform="sviip")
            row.columnconfigure(3, weight=1, uniform="sviip")
            if editable:
                vlan_w = ttk.Entry(row)
                vlan_w.grid(row=0, column=0, sticky="ew", padx=1)
                vlan_w.insert(0, saved.get("vlan") or vlan)
                _attach_context_menu(vlan_w)
            else:
                vlan_w = vlan
                ttk.Label(row, text=f"Vlan{vlan}", anchor="w").grid(
                    row=0, column=0, sticky="ew", padx=1)
            desc_w = ttk.Entry(row)
            desc_w.grid(row=0, column=1, sticky="ew", padx=1)
            desc_w.insert(0, saved.get("desc") or desc)
            _attach_context_menu(desc_w)
            ip = ttk.Entry(row); ip.grid(row=0, column=2, sticky="ew", padx=1)
            mask = ttk.Entry(row); mask.grid(row=0, column=3, sticky="ew", padx=1)
            _attach_context_menu(ip)
            _attach_context_menu(mask)
            if saved:
                ip.insert(0, saved.get("ip", ""))
                mask.insert(0, saved.get("mask", ""))
            if not ip.get() and default_ip:
                ip.insert(0, default_ip)
            if not mask.get() and default_mask:
                mask.insert(0, default_mask)
            self.svi_ip_rows.append({
                "frame": row, "vlan": vlan_w, "desc": desc_w,
                "ip": ip, "mask": mask, "editable": editable,
                "helpers": saved.get("helpers") or helpers,
                "profile_vlan": vlan,
            })

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

    def _on_gateway_changed(self, _event=None):
        self._refresh_static_preview()
        self._sync_gateway_to_bgp()

    def _set_bgp_field_from_gateway(self, entry, dg, prev_dg):
        """Fill a BGP field from Default Gateway unless the user overrode it."""
        if not dg:
            return
        cur = entry.get().strip()
        if not cur or (prev_dg and cur == prev_dg):
            entry.delete(0, "end")
            entry.insert(0, dg)

    def _sync_gateway_to_bgp(self):
        """One-way sync: Default Gateway -> ISP Gateway and Peer IP fields.
        Blank fields are filled; fields still matching the previous gateway
        value are updated. Manually edited BGP values are left alone."""
        if not getattr(self, "bgp_inst_blocks", None):
            return
        dg = self.gateway.get().strip() if hasattr(self, "gateway") else ""
        if not dg:
            return
        prev = getattr(self, "_last_synced_gateway", "")
        for blk in self.bgp_inst_blocks:
            self._set_bgp_field_from_gateway(blk["isp_gateway"], dg, prev)
            for peer in blk["peers"]:
                self._set_bgp_field_from_gateway(peer["ip"], dg, prev)
        self._last_synced_gateway = dg

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
            default_peer_asn = str(inst.get("peer_asn") or "").strip()
            if not slots and default_peer_asn:
                slots = [{"peer_asn": default_peer_asn, "description": ""}]
            self._add_bgp_inst_block(
                local_asn,
                default_peer_asn,
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
                           "  Add slots under Profiles -> BGP."
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

    def _clear_sw_users(self):
        for r in self.sw_user_rows:
            r["frame"].destroy()
        self.sw_user_rows.clear()

    def _del_row(self, frame, lst):
        lst[:] = [r for r in lst if r["frame"] is not frame]
        frame.destroy()

    def _add_sw_user(self, data=None):
        row = ttk.Frame(self.sw_user_frame); row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=2, uniform="swusr")
        row.columnconfigure(1, weight=2, uniform="swusr")
        row.columnconfigure(2, weight=1, uniform="swusr")
        name = ttk.Entry(row); name.grid(row=0, column=0, sticky="ew", padx=1)
        pw   = ttk.Entry(row); pw.grid(  row=0, column=1, sticky="ew", padx=1)
        priv = ttk.Entry(row); priv.grid(row=0, column=2, sticky="ew", padx=1)
        for w in (name, pw, priv):
            _attach_context_menu(w)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.sw_user_rows)
                   ).grid(row=0, column=3, padx=(6, 1))
        if data:
            name.insert(0, data.get("name", "") or data.get("username", ""))
            pw.insert(0, data.get("password", "") or "")
            priv.insert(0, str(data.get("privilege", "") or ""))
        else:
            priv.insert(0, "15")
        self.sw_user_rows.append({"frame": row, "name": name,
                                  "pw": pw, "priv": priv})

    def _collect_sw_users(self):
        out = []
        for r in self.sw_user_rows:
            uname = r["name"].get().strip()
            if not uname:
                continue
            pw = r["pw"].get().strip()
            priv_raw = r["priv"].get().strip()
            try:
                priv = int(priv_raw) if priv_raw else 15
            except ValueError:
                priv = 15
            out.append({"name": uname, "password": pw, "privilege": priv})
        return out

    def _sw_dict(self):
        # ttk.Entry.get() works whether or not the widget is disabled
        users = self._collect_sw_users()
        first = users[0] if users else {}
        sw = {
            "hostname":        self.hostname.get().strip(),
            "users":           users,
            # Backward-compat singulars - the renderer prefers `users` when
            # present but legacy paths can still read these two keys.
            "local_username":  first.get("name", ""),
            "enable_secret":   self.secret.get().strip(),
            "admin_password":  first.get("password", ""),
            "domain_name":     self.domain.get().strip(),
            "mgmt_ip":         self.mgmt_ip.get().strip(),
            "mgmt_mask":       self.mgmt_mask.get().strip(),
            "default_gateway": self.gateway.get().strip(),
            "oob_ip":          self.oob_ip.get().strip(),
            "oob_mask":        self.oob_mask.get().strip(),
            "work_order":      self.work_order.get().strip(),
            "vlan_definitions": self.sw_vlans_text.get("1.0", "end").strip(),
        }
        # L3 fields - only meaningful when the selected profile is L3,
        # but always populated so the renderer can read them safely
        sw.update(_collect_l3_sw_from_grids(
            self.l3_gen_grids,
            editable_vlan=bool(
                self.app.profiles.get(self.profile_cb.get(), {}).get(
                    "allow_per_switch_vlans")),
        ))
        sw["router_id"] = self.router_id.get().strip()
        sw["routed_iface_ips"] = {
            r["iface_name"]: {"ip": r["ip"].get().strip(),
                              "mask": r["mask"].get().strip()}
            for r in self.l3_ip_rows
        }
        # When the profile leaves routed_mgmt.interface blank, the user
        # types the uplink IP in the Routed Interfaces grid. Merge that
        # site-wide override into any per-port rows that are still blank.
        site_rm = _site_routed_mgmt_override(sw)
        if site_rm:
            for entry in sw["routed_iface_ips"].values():
                if not entry.get("ip") and (site_rm.get("ip") or "").strip():
                    entry["ip"] = site_rm["ip"].strip()
                if not entry.get("mask") and (site_rm.get("mask") or "").strip():
                    entry["mask"] = site_rm["mask"].strip()
        svi_ips = {}
        sw_svis = []
        pn = self.profile_cb.get()
        profile = self.app.profiles.get(pn, {}) or {}
        vlan_remap = _vlan_id_remap(profile, sw)
        for r in self.svi_ip_rows:
            if r.get("editable"):
                vlan = r["vlan"].get().strip()
                profile_vlan = (r.get("profile_vlan") or "").strip()
                if not vlan:
                    continue
                if profile_vlan and vlan == profile_vlan and profile_vlan in vlan_remap:
                    vlan = vlan_remap[profile_vlan]
            else:
                vlan = r["vlan"]
            desc = r["desc"].get().strip() if r.get("desc") else ""
            ip_val = r["ip"].get().strip()
            mask_val = r["mask"].get().strip()
            helpers_raw = r.get("helpers") or ""
            if isinstance(helpers_raw, str):
                helpers = [h.strip() for h in helpers_raw.split(",")
                           if h.strip()]
            else:
                helpers = list(helpers_raw or [])
            sw_svis.append({
                "vlan": vlan,
                "description": desc,
                "ip": ip_val,
                "mask": mask_val,
                "helper_addresses": helpers,
            })
            svi_ips[vlan] = {"ip": ip_val, "mask": mask_val}
            if desc:
                svi_ips[vlan]["description"] = desc
        sw["svi_ips"] = svi_ips
        if sw_svis:
            sw["svis"] = sw_svis
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
        # Re-sync the L3 IP grid against the CURRENT Step-2 port
        # assignments before reading them. Catches the case where the
        # user edited an interface on Step 2 after the last forward
        # navigation, which would otherwise leave routed_iface_ips
        # keyed by stale interface names and the renderer would emit
        # blank ip address lines.
        if pn and pn in self.app.profiles:
            profile_chk = self.app.profiles[pn]
            if profile_chk.get("layer3"):
                self._populate_l3_ip_rows()
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

    def _push(self):
        txt = self.preview.get("1.0", "end").strip()
        if not txt:
            _dialog("Empty", "Generate a config first.")
            return
        _SerialPushDialog(self.winfo_toplevel(), txt,
                          hostname=self.hostname.get().strip())

    def _copy_section(self, name):
        text = self._sections.get(name, "").strip()
        if not text:
            _dialog("Empty", f"The '{name}' section is empty.", "warning")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        _dialog("Copied", f"'{name}' copied to clipboard.")


