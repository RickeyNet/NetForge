"""Site Profiles tab."""

import json

import tkinter as tk
from tkinter import ttk

from netforge.data.storage import save_json
from netforge.render import (
    _normalize_l3_sections,
    _ntp_commands_for_edit,
    _ospf_config_for_edit,
)
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
from netforge.ui.l3_grid import L3EntryGrid, _L3_UI_ALIAS
from netforge.ui.theme import C
from netforge.ui.widgets import PanedWindow, ScrollFrame, _CheckList


# --- BGP advertising-option parsing (text fields <-> structured lists) ---
def _parse_bgp_networks(text):
    """'NETWORK [MASK]' per line -> [{'network':..., 'mask':...}]."""
    out = []
    for ln in (text or "").splitlines():
        toks = ln.split()
        if not toks:
            continue
        out.append({"network": toks[0],
                    "mask": toks[1] if len(toks) > 1 else ""})
    return out


def _parse_bgp_redistribute(text):
    """One redistribute source per line -> ['connected', 'ospf 1', ...]."""
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _parse_bgp_aggregates(text):
    """'PREFIX [MASK] [summary-only]' per line -> list of dicts."""
    out = []
    for ln in (text or "").splitlines():
        toks = ln.split()
        if not toks:
            continue
        summary = any(t.lower() == "summary-only" for t in toks[1:])
        rest = [t for t in toks[1:] if t.lower() != "summary-only"]
        out.append({"prefix": toks[0],
                    "mask": rest[0] if rest else "",
                    "summary_only": summary})
    return out


def _bgp_networks_to_text(nets):
    return "\n".join(
        f"{n.get('network', '')} {n.get('mask', '')}".strip()
        for n in (nets or []))


def _bgp_aggregates_to_text(aggs):
    lines = []
    for a in (aggs or []):
        parts = [a.get("prefix", ""), a.get("mask", "")]
        if a.get("summary_only"):
            parts.append("summary-only")
        lines.append(" ".join(p for p in parts if p))
    return "\n".join(lines)


class ProfilesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.var_rows = []
        self.pa_rows  = []
        self.svi_rows = []
        self.l3_profile_grids = {}
        self.acl_blocks = []   # list of dicts: one per ACL editor block
        self.bgp_blocks = []   # list of dicts: one per BGP instance block
        self._build()

    def _build(self):
        paned = PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # -- left: list --
        left = ttk.Frame(paned); paned.add(left, weight=0)
        ttk.Label(left, text="Site Profiles",
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
                                        values=self.app._visible_base_set_names())
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
        self.allow_sw_vlans = tk.BooleanVar(value=False)
        ttk.Checkbutton(form,
                        text="Allow per-switch VLAN overrides in Step 3",
                        variable=self.allow_sw_vlans
                        ).pack(anchor="w", padx=5, pady=(2, 0))
        ttk.Label(form, style="Hint.TLabel",
                  text="  When on, Generate Step 3 shows a VLAN editor\n"
                       "  pre-filled with this block. Step 3 edits replace\n"
                       "  these definitions for that one switch only.\n"
                       "  On L3 profiles, SVI VLAN IDs can also be edited\n"
                       "  per switch so they stay in sync with VLAN overrides."
                  ).pack(anchor="w", padx=5, pady=(0, 2))
        self.vlans_text = tk.Text(form, height=10, font=("Consolas", 9),
                                  bg=C["bg_input"], fg=C["fg"],
                                  insertbackground=C["fg"],
                                  selectbackground=C["sel_bg"],
                                  relief="flat", bd=2, wrap="word")
        self.vlans_text.pack(fill="x", padx=5, pady=4)
        _attach_context_menu(self.vlans_text)
        _autosize_textarea(self.vlans_text, min_h=4, max_h=40)

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

        # Local Users table - one IOS `username` line per row at render time.
        users_lf = ttk.LabelFrame(cred_lf, text="Local Users", padding=5)
        users_lf.pack(fill="x", padx=2, pady=2)

        users_hint = ttk.Frame(users_lf); users_hint.pack(fill="x", pady=(0, 4))
        ttk.Label(users_hint, style="Hint.TLabel",
                  text="  One row per local user. Each row renders as\n"
                       "  `username NAME privilege P secret PW`. Step 3\n"
                       "  loads an editable copy for each generated switch."
                  ).pack(side="left", anchor="w", padx=2)
        ttk.Button(users_hint, text="+ Add User",
                   command=self._add_user
                   ).pack(side="right", anchor="ne", padx=(6, 1))

        uh = ttk.Frame(users_lf); uh.pack(fill="x")
        uh.columnconfigure(0, weight=2, uniform="usr")
        uh.columnconfigure(1, weight=2, uniform="usr")
        uh.columnconfigure(2, weight=1, uniform="usr")
        ttk.Label(uh, text="Username", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(uh, text="Password", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Label(uh, text="Privilege", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=1)
        ttk.Frame(uh, width=30).grid(row=0, column=3, padx=(6, 1))
        self.user_frame = ttk.Frame(users_lf); self.user_frame.pack(fill="x")
        self.user_rows = []

        self.cred_enable_e = _field(cred_lf, "Enable Secret")

        # -- DNS / NTP services --
        _section(form, "Services (DNS / NTP)")
        ttk.Label(form, style="Hint.TLabel",
                  text="  Site-wide DNS, NTP, and clock settings emitted in\n"
                       "  the Global section. Name Servers accepts a comma-\n"
                       "  separated list. Timezone takes a name + offset\n"
                       "  (e.g. EST -5).  NTP is a free-form text box - paste\n"
                       "  the exact IOS commands you want emitted."
                  ).pack(anchor="w", padx=5, pady=(4, 0))

        svc_lf = ttk.LabelFrame(form, text="DNS / NTP", padding=5)
        svc_lf.pack(fill="x", padx=5, pady=5)

        self.dns_servers_e  = _field(svc_lf, "Name Servers")
        self.clock_tz_e     = _field(svc_lf, "Clock Timezone")
        self.clock_summer_e = _field(svc_lf, "Clock Summer-Time")

        ttk.Label(svc_lf, text="NTP Commands", width=26, anchor="nw").pack(
            anchor="w", padx=(0, 6), pady=(6, 0))
        self.ntp_text = _autosize_textarea(
            _textarea(svc_lf, "", "", h=2), min_h=2, max_h=20)
        ttk.Label(svc_lf, style="Hint.TLabel",
                  text="  Lines pasted here are emitted verbatim in the\n"
                       "  Global section.  Example:\n"
                       "    ntp authenticate\n"
                       "    ntp authentication-key 1 md5 <key>\n"
                       "    ntp trusted-key 1\n"
                       "    ntp source Loopback1\n"
                       "    ntp access-group peer 10\n"
                       "    ntp server 10.0.0.2 key 1\n"
                       "    access-list 10 permit host 10.0.0.2"
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
        # Header uses the same 2-column grid layout as the rows below
        # (uniform width, equal weight) so labels line up exactly over
        # the Key and Value entries no matter how wide the form is.
        vh.columnconfigure(0, weight=1, uniform="varcol")
        vh.columnconfigure(1, weight=1, uniform="varcol")
        ttk.Label(vh, text="Key", anchor="w"
                  ).grid(row=0, column=0, sticky="ew", padx=1)
        ttk.Label(vh, text="Value", anchor="w"
                  ).grid(row=0, column=1, sticky="ew", padx=1)
        ttk.Button(vh, text="+ Add Variable",
                   command=self._add_var
                   ).grid(row=0, column=2, padx=2, sticky="e")
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
                       "  SVIs as gateways, BGP). Per-switch values like\n"
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

        for kind in ("loopback", "routed_mgmt", "mgmt_svi"):
            grid = L3EntryGrid(kind, mode="profile").build_profile(self.l3_body)
            self.l3_profile_grids[kind] = grid
            alias = _L3_UI_ALIAS[kind]
            setattr(self, f"{alias}_sec_lf", grid.lf)
            setattr(self, f"{alias}_sec_enabled", grid.enabled)
            setattr(self, f"{alias}_frame", grid.row_frame)
            setattr(self, f"{alias}_rows", grid.rows)

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

        # OSPF (raw IOS paste)
        self.ospf_lf = ttk.LabelFrame(self.l3_body, text="OSPF", padding=5)
        self.ospf_lf.pack(fill="x", padx=5, pady=4)
        ttk.Label(self.ospf_lf, style="Hint.TLabel",
                  text="  Paste the site-wide OSPF block here. Lines emit\n"
                       "  verbatim in Routing. Router-ID can be included\n"
                       "  here or filled per switch in Generate Config."
                  ).pack(anchor="w", padx=2, pady=(0, 4))
        self.ospf_text = tk.Text(
            self.ospf_lf, height=2, font=("Consolas", 9),
            bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
            selectbackground=C["sel_bg"], relief="flat", bd=2, wrap="none")
        self.ospf_text.pack(fill="x", padx=2, pady=(0, 2))
        _attach_context_menu(self.ospf_text)
        _autosize_textarea(self.ospf_text, min_h=2, max_h=20)

        # BGP - one or more instances, each rendered as its own
        # `router bgp <asn>` block. Same +Add/X pattern as ACLs.
        # When empty the section collapses to the title bar + Add button.
        self.bgp_outer_lf = ttk.LabelFrame(
            self.l3_body, text="BGP", padding=5)
        self.bgp_outer_lf.pack(fill="x", padx=5, pady=4)
        bgp_top = ttk.Frame(self.bgp_outer_lf); bgp_top.pack(fill="x")
        self._bgp_add_btn = ttk.Button(bgp_top, text="+ Add BGP",
                   command=lambda: self._add_bgp_block())
        self._bgp_add_btn.pack(side="right", anchor="ne", padx=(6, 1))
        self.bgp_container = ttk.Frame(self.bgp_outer_lf)

        # ACLs (site-wide named access-lists)
        self.acl_lf = ttk.LabelFrame(self.l3_body, text="Access Lists", padding=5)
        self.acl_lf.pack(fill="x", padx=5, pady=4)
        acl_top = ttk.Frame(self.acl_lf); acl_top.pack(fill="x")
        self._acl_add_btn = ttk.Button(acl_top, text="+ Add ACL",
                   command=lambda: self._add_acl_block())
        self._acl_add_btn.pack(side="right", anchor="ne", padx=(6, 1))
        self.acl_container = ttk.Frame(self.acl_lf)

        self._update_bgp_collapsed()
        self._update_acl_collapsed()
        self._refresh()

    # -- list helpers --
    def _refresh(self):
        if self.show_hidden.get():
            names = list(self.app.profiles.keys())
        else:
            names = self.app.visible_keys("profiles")
        self.lb.populate(names)
        for n in names:
            if self.app.is_hidden("profiles", n):
                self.lb.set_dim(n, True)

    def _toggle_hide(self):
        _toggle_hidden_batch(self, "profiles", "profile")

    # -- variable rows --
    def _clear_vars(self):
        for r in self.var_rows:
            r["frame"].destroy()
        self.var_rows.clear()

    def _add_var(self, data=None):
        row = ttk.Frame(self.var_frame); row.pack(fill="x", pady=1)
        # Key and Value share equal column weight so they stretch with
        # the form. uniform="varcol" matches the header above so the
        # two columns line up perfectly regardless of label widths.
        row.columnconfigure(0, weight=1, uniform="varcol")
        row.columnconfigure(1, weight=1, uniform="varcol")
        k = ttk.Entry(row)
        k.grid(row=0, column=0, sticky="ew", padx=1)
        v = ttk.Entry(row)
        v.grid(row=0, column=1, sticky="ew", padx=1)
        _attach_context_menu(k)
        _attach_context_menu(v)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.var_rows)
                   ).grid(row=0, column=2, padx=2)
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

    def _clear_users(self):
        for r in self.user_rows:
            r["frame"].destroy()
        self.user_rows.clear()

    def _add_user(self, data=None):
        row = ttk.Frame(self.user_frame); row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=2, uniform="usr")
        row.columnconfigure(1, weight=2, uniform="usr")
        row.columnconfigure(2, weight=1, uniform="usr")
        name = ttk.Entry(row); name.grid(row=0, column=0, sticky="ew", padx=1)
        pw   = ttk.Entry(row); pw.grid(  row=0, column=1, sticky="ew", padx=1)
        priv = ttk.Entry(row); priv.grid(row=0, column=2, sticky="ew", padx=1)
        for w in (name, pw, priv):
            _attach_context_menu(w)
        ttk.Button(row, text="X", width=3, style="Del.TButton",
                   command=lambda: self._del_row(row, self.user_rows)
                   ).grid(row=0, column=3, padx=(6, 1))
        if data:
            name.insert(0, data.get("name", "") or data.get("username", ""))
            pw.insert(0, data.get("password", "") or "")
            priv.insert(0, str(data.get("privilege", "") or ""))
        else:
            priv.insert(0, "15")
        self.user_rows.append({"frame": row, "name": name,
                               "pw": pw, "priv": priv})

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

    # -- ACL editor --
    _ACL_ACTIONS = ("permit", "deny", "remark")
    _ACL_PROTOCOLS = ("ip", "tcp", "udp", "icmp", "gre", "esp", "ahp",
                      "eigrp", "ospf", "pim", "igmp", "sctp")

    def _update_acl_collapsed(self):
        """Show only the Add button when no ACLs; expand once blocks exist."""
        if self.acl_blocks:
            if not self.acl_container.winfo_ismapped():
                self.acl_container.pack(fill="x")
        elif self.acl_container.winfo_ismapped():
            self.acl_container.pack_forget()

    def _update_bgp_collapsed(self):
        """Show only the Add button when no BGP instances; expand once blocks exist."""
        if self.bgp_blocks:
            if not self.bgp_container.winfo_ismapped():
                self.bgp_container.pack(fill="x")
        elif self.bgp_container.winfo_ismapped():
            self.bgp_container.pack_forget()

    def _sync_acl_block_rules(self, block):
        """Hide the rules grid header until the ACL has at least one rule."""
        has_rules = bool(block["rules"])
        rules_frame = block["rules_frame"]
        btn_row = block["btn_row"]
        if has_rules:
            if not rules_frame.winfo_ismapped():
                rules_frame.pack(fill="x", pady=(6, 0), before=btn_row)
        elif rules_frame.winfo_ismapped():
            rules_frame.pack_forget()

    def _sync_bgp_block_slots(self, block):
        """Hide peer-slot column headers until at least one slot exists."""
        has_slots = bool(block["slots"])
        if has_slots:
            if not block["slots_hdr"].winfo_ismapped():
                block["slots_hdr"].pack(fill="x")
            block["peer_hint"].pack_forget()
            block["slots_hint"].pack_forget()
        else:
            if block["slots_hdr"].winfo_ismapped():
                block["slots_hdr"].pack_forget()
            block["peer_hint"].pack_forget()
            block["slots_hint"].pack_forget()

    def _clear_acls(self):
        for blk in self.acl_blocks:
            blk["frame"].destroy()
        self.acl_blocks.clear()
        self._update_acl_collapsed()

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
        ttk.Button(top, text="↓", width=3,
                   command=lambda f=blk_frame: self._move_acl_block(f, 1)
                   ).pack(side="right", padx=(0, 2))
        ttk.Button(top, text="↑", width=3,
                   command=lambda f=blk_frame: self._move_acl_block(f, -1)
                   ).pack(side="right", padx=(0, 2))

        # Rules grid: header + every rule row live inside this single
        # frame and use shared `grid` columns, so column widths line up
        # exactly between the header labels and the field widgets below.
        rules_frame = ttk.Frame(blk_frame)
        for col in (2, 3, 4, 5):
            rules_frame.columnconfigure(col, weight=1, uniform="acladdrs")
        rules_frame.columnconfigure(6, minsize=36)
        rules_frame.columnconfigure(7, minsize=52)

        hdr_kw = dict(sticky="ew", padx=1)
        ttk.Label(rules_frame, text="Action", anchor="w"
                  ).grid(row=0, column=0, **hdr_kw)
        ttk.Label(rules_frame, text="Proto", anchor="w"
                  ).grid(row=0, column=1, **hdr_kw)
        ttk.Label(rules_frame, text="Source", anchor="w"
                  ).grid(row=0, column=2, **hdr_kw)
        ttk.Label(rules_frame, text="Source Wildcard", anchor="w"
                  ).grid(row=0, column=3, **hdr_kw)
        ttk.Label(rules_frame, text="Destination", anchor="w"
                  ).grid(row=0, column=4, **hdr_kw)
        ttk.Label(rules_frame, text="Dest Wildcard", anchor="w"
                  ).grid(row=0, column=5, **hdr_kw)
        ttk.Label(rules_frame, text="Log", anchor="center"
                  ).grid(row=0, column=6, sticky="ew", padx=2)
        ttk.Label(rules_frame, text="Log-In", anchor="center"
                  ).grid(row=0, column=7, sticky="ew", padx=2)
        ttk.Label(rules_frame, text="Del", anchor="center"
                  ).grid(row=0, column=8, sticky="ew", padx=2)
        ttk.Label(rules_frame, text="Move", anchor="center"
                  ).grid(row=0, column=9, sticky="ew", padx=2)

        btn_row = ttk.Frame(blk_frame); btn_row.pack(fill="x", pady=(4, 0))
        block = {"frame": blk_frame, "name": name_e, "type": type_cb,
                 "rules": rule_rows, "rules_frame": rules_frame,
                 "btn_row": btn_row, "next_row": 1}
        ttk.Button(btn_row, text="+ Add Rule",
                   command=lambda b=block: self._add_acl_rule(b)
                   ).pack(side="left")

        self.acl_blocks.append(block)
        self._update_acl_collapsed()

        if data:
            name_e.insert(0, data.get("name", ""))
            type_cb.set(data.get("type", "extended") or "extended")
            for rule in data.get("rules", []) or []:
                self._add_acl_rule(block, rule)
        self._sync_acl_block_rules(block)

    def _del_acl_block(self, frame):
        self.acl_blocks[:] = [b for b in self.acl_blocks
                              if b["frame"] is not frame]
        frame.destroy()
        self._update_acl_collapsed()

    def _move_acl_block(self, frame, direction):
        idx = next((i for i, b in enumerate(self.acl_blocks)
                    if b["frame"] is frame), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.acl_blocks):
            return
        self.acl_blocks[idx], self.acl_blocks[new_idx] = (
            self.acl_blocks[new_idx], self.acl_blocks[idx])
        for blk in self.acl_blocks:
            blk["frame"].pack_forget()
        for blk in self.acl_blocks:
            blk["frame"].pack(fill="x", pady=(0, 6))

    def _add_acl_rule(self, block, data=None):
        # All rule widgets grid directly into the shared rules_frame so
        # column widths stay aligned with the header row above.
        # Grid columns:  0 action | 1 proto | 2 src | 3 src_wc |
        #                4 dst    | 5 dst_wc | 6 log | 7 log-in | 8 X
        parent = block["rules_frame"]
        r = block["next_row"]
        block["next_row"] = r + 1
        gkw = dict(row=r, sticky="ew", padx=1, pady=1)

        action_cb = ttk.Combobox(parent, width=8, state="readonly",
                                 values=list(self._ACL_ACTIONS))
        action_cb.bind("<MouseWheel>", lambda _e: "break")
        action_cb.grid(column=0, **gkw)
        proto_e = ttk.Combobox(parent, width=6,
                               values=list(self._ACL_PROTOCOLS))
        proto_e.bind("<MouseWheel>", lambda _e: "break")
        src_e   = ttk.Entry(parent)
        srcwc_e = ttk.Entry(parent)
        dst_e   = ttk.Entry(parent)
        dstwc_e = ttk.Entry(parent)
        proto_e.grid(column=1, **gkw)
        src_e.grid(  column=2, **gkw)
        srcwc_e.grid(column=3, **gkw)
        dst_e.grid(  column=4, **gkw)
        dstwc_e.grid(column=5, **gkw)
        log_var = tk.BooleanVar(value=False)
        log_input_var = tk.BooleanVar(value=False)

        def _on_log_toggle():
            if log_var.get():
                log_input_var.set(False)

        def _on_log_input_toggle():
            if log_input_var.get():
                log_var.set(False)

        log_cb = ttk.Checkbutton(parent, variable=log_var,
                               command=_on_log_toggle)
        log_cb.grid(row=r, column=6, padx=2, pady=1)
        log_input_cb = ttk.Checkbutton(parent, variable=log_input_var,
                                       command=_on_log_input_toggle)
        log_input_cb.grid(row=r, column=7, padx=2, pady=1)
        for w in (proto_e, src_e, srcwc_e, dst_e, dstwc_e):
            _attach_context_menu(w)
        del_btn = ttk.Button(parent, text="X", width=3, style="Del.TButton",
                             command=lambda: self._del_acl_rule(rule, block))
        del_btn.grid(row=r, column=8, padx=2, pady=1)
        mv_frm = ttk.Frame(parent)
        mv_frm.grid(row=r, column=9, padx=2, pady=1)
        ttk.Button(mv_frm, text="↑", width=2,
                   command=lambda: self._move_acl_rule(rule, block, -1)
                   ).pack(side="left")
        ttk.Button(mv_frm, text="↓", width=2,
                   command=lambda: self._move_acl_rule(rule, block, 1)
                   ).pack(side="left")

        rule_widgets = (action_cb, proto_e, src_e, srcwc_e,
                        dst_e, dstwc_e, log_cb, log_input_cb, del_btn)
        rule = {"widgets": rule_widgets, "row_idx": r,
                "action": action_cb, "proto": proto_e,
                "src": src_e, "src_wc": srcwc_e,
                "dst": dst_e, "dst_wc": dstwc_e,
                "log": log_var, "log_input": log_input_var,
                "del_btn": del_btn}

        # When the action is 'remark', collapse the rule fields into a
        # single text entry that spans columns 1-6 (everything between
        # the action combobox and the delete button). Row width and
        # sash alignment stay identical to permit/deny rows.
        def _refresh_action_layout(*_):
            act = action_cb.get() or "permit"
            if act == "remark":
                for w in (proto_e, src_e, srcwc_e, dst_e, dstwc_e,
                          log_cb, log_input_cb):
                    w.grid_remove()
                rmk = rule.get("remark")
                if rmk is None:
                    rmk = ttk.Entry(parent)
                    _attach_context_menu(rmk)
                    rule["remark"] = rmk
                rmk.grid(row=rule["row_idx"], column=1, columnspan=7,
                         sticky="ew", padx=1, pady=1)
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
                log_input_cb.grid()

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
                log_input_var.set(bool(data.get("log_input", False)))
        else:
            action_cb.set("permit")
            proto_e.insert(0, "ip")

        block["rules"].append(rule)
        self._sync_acl_block_rules(block)

    def _del_acl_rule(self, rule, block):
        for w in rule["widgets"]:
            w.destroy()
        rmk = rule.get("remark")
        if rmk is not None:
            rmk.destroy()
        block["rules"][:] = [r for r in block["rules"] if r is not rule]
        self._sync_acl_block_rules(block)

    def _move_acl_rule(self, rule, block, direction):
        rules = block["rules"]
        idx = next((i for i, r in enumerate(rules) if r is rule), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(rules):
            return
        a_data = self._read_acl_rule(rules[idx])
        b_data = self._read_acl_rule(rules[new_idx])
        self._write_acl_rule(rules[idx], b_data)
        self._write_acl_rule(rules[new_idx], a_data)

    def _read_acl_rule(self, rule):
        act = rule["action"].get() or "permit"
        if act == "remark":
            rmk = rule.get("remark")
            return {"action": "remark", "text": rmk.get() if rmk else ""}
        return {
            "action": act,
            "protocol": rule["proto"].get(),
            "source": rule["src"].get(),
            "source_wildcard": rule["src_wc"].get(),
            "dest": rule["dst"].get(),
            "dest_wildcard": rule["dst_wc"].get(),
            "log": bool(rule["log"].get()),
            "log_input": bool(rule["log_input"].get()),
        }

    def _write_acl_rule(self, rule, data):
        act = data.get("action", "permit") or "permit"
        rule["action"].set(act)
        rule["action"].event_generate("<<ComboboxSelected>>")
        if act == "remark":
            rmk = rule.get("remark")
            if rmk:
                rmk.delete(0, "end")
                rmk.insert(0, data.get("text", ""))
        else:
            for widget, key, default in (
                (rule["proto"],  "protocol",        "ip"),
                (rule["src"],    "source",          ""),
                (rule["src_wc"], "source_wildcard", ""),
                (rule["dst"],    "dest",            ""),
                (rule["dst_wc"], "dest_wildcard",   ""),
            ):
                widget.delete(0, "end")
                widget.insert(0, data.get(key, default) or default)
            rule["log"].set(bool(data.get("log", False)))
            rule["log_input"].set(bool(data.get("log_input", False)))

    # -- BGP instance blocks --
    def _clear_bgp_blocks(self):
        for blk in self.bgp_blocks:
            blk["frame"].destroy()
        self.bgp_blocks.clear()
        self._update_bgp_collapsed()

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
        peer_hint = ttk.Label(blk_frame, style="Hint.TLabel",
                  text="  Default Peer ASN pre-fills new peer rows below\n"
                       "  and per-switch peers in Generate Config. Each peer\n"
                       "  carries its own ASN, so peers from different\n"
                       "  upstreams within this instance are fine.")

        slots_lf = ttk.LabelFrame(blk_frame, text="Peer Slots", padding=5)
        slots_lf.pack(fill="x", padx=2, pady=(4, 0))

        hint_row = ttk.Frame(slots_lf); hint_row.pack(fill="x", pady=(0, 4))
        slots_hint = ttk.Label(hint_row, style="Hint.TLabel",
                  text="  Each slot describes one BGP neighbor that will\n"
                       "  exist on every switch built from this profile.\n"
                       "  Peer IP and password are entered per-switch in\n"
                       "  Generate Config.")

        slot_frame = ttk.Frame(slots_lf)
        block = {"frame": blk_frame, "local_asn": local_e,
                 "peer_asn": peer_asn_e, "slot_frame": slot_frame,
                 "slots_lf": slots_lf, "peer_hint": peer_hint,
                 "slots_hint": slots_hint, "slots_hdr": None,
                 "slots": []}
        ttk.Button(hint_row, text="+ Add Slot",
                   command=lambda b=block: self._add_bgp_slot(b)
                   ).pack(side="right", anchor="ne", padx=(6, 1))

        ph = ttk.Frame(slots_lf)
        block["slots_hdr"] = ph
        ph.columnconfigure(0, weight=1, uniform="bgpslots")
        ph.columnconfigure(1, weight=3, uniform="bgpslots")
        ttk.Label(ph, text="Remote ASN", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=1)
        ttk.Label(ph, text="Description", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=1)
        ttk.Frame(ph, width=30).grid(row=0, column=2, padx=(6, 1))

        slot_frame.pack(fill="x")

        # Advertising options (optional, site-wide for this instance).
        adv_lf = ttk.LabelFrame(blk_frame, text="Advertising", padding=5)
        adv_lf.pack(fill="x", padx=2, pady=(4, 0))

        def _adv_text(label, hint):
            ttk.Label(adv_lf, text=label, anchor="w").pack(anchor="w")
            ttk.Label(adv_lf, style="Hint.TLabel", text=hint).pack(
                anchor="w", padx=2)
            t = tk.Text(adv_lf, height=2, font=("Consolas", 9),
                        bg=C["bg_input"], fg=C["fg"],
                        insertbackground=C["fg"],
                        selectbackground=C["sel_bg"], relief="flat",
                        bd=2, wrap="none")
            t.pack(fill="x", padx=2, pady=(0, 4))
            _attach_context_menu(t)
            _autosize_textarea(t, min_h=2, max_h=12)
            return t

        block["networks_text"] = _adv_text(
            "Networks",
            "  One per line: NETWORK MASK  (e.g. 10.0.0.0 255.0.0.0)")
        block["redistribute_text"] = _adv_text(
            "Redistribute",
            "  One per line  (e.g. connected / static / ospf 1)")
        block["aggregates_text"] = _adv_text(
            "Aggregate addresses",
            "  One per line: PREFIX MASK [summary-only]")

        self.bgp_blocks.append(block)
        self._update_bgp_collapsed()

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
            block["networks_text"].insert(
                "1.0", _bgp_networks_to_text(data.get("networks")))
            block["redistribute_text"].insert(
                "1.0", "\n".join(str(r) for r in
                                 (data.get("redistribute") or [])))
            block["aggregates_text"].insert(
                "1.0", _bgp_aggregates_to_text(data.get("aggregates")))
        else:
            local_e.insert(0, "65000")
            peer_asn_e.insert(0, "65001")
        self._sync_bgp_block_slots(block)

    def _del_bgp_block(self, frame):
        self.bgp_blocks[:] = [b for b in self.bgp_blocks
                              if b["frame"] is not frame]
        frame.destroy()
        self._update_bgp_collapsed()

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
        self._sync_bgp_block_slots(block)

    def _del_bgp_slot(self, row, block):
        block["slots"][:] = [r for r in block["slots"]
                             if r["frame"] is not row]
        row.destroy()
        self._sync_bgp_block_slots(block)

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
            inst = {
                "local_asn": local_asn,
                "peer_asn":  blk["peer_asn"].get().strip(),
                "slots":     slots,
            }
            # Only persist advertising lists when the user entered some,
            # so existing profiles stay unchanged.
            nets = _parse_bgp_networks(
                blk["networks_text"].get("1.0", "end"))
            reds = _parse_bgp_redistribute(
                blk["redistribute_text"].get("1.0", "end"))
            aggs = _parse_bgp_aggregates(
                blk["aggregates_text"].get("1.0", "end"))
            if nets:
                inst["networks"] = nets
            if reds:
                inst["redistribute"] = reds
            if aggs:
                inst["aggregates"] = aggs
            out.append(inst)
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
                        "log_input": bool(r["log_input"].get()),
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

        self.base_set_cb["values"] = self.app._visible_base_set_names()
        self.base_set_cb.set(p.get("base_set", "") or "")

        creds = p.get("credentials", {}) or {}
        self._clear_users()
        users = creds.get("users") or []
        if not users:
            # Migrate the old single-credential shape into a one-row list.
            legacy_name = creds.get("local_username", "")
            legacy_pw   = creds.get("admin_password", "")
            if legacy_name or legacy_pw:
                users = [{"name": legacy_name, "password": legacy_pw,
                          "privilege": 15}]
        for u in users:
            self._add_user(u)
        self.cred_enable_e.delete(0, "end")
        self.cred_enable_e.insert(0, creds.get("enable_secret", "") or "")

        svc = p.get("services", {}) or {}
        dns_list = svc.get("dns_servers") or []
        if isinstance(dns_list, list):
            dns_list = ", ".join(str(x) for x in dns_list)
        self.dns_servers_e.delete(0, "end")
        self.dns_servers_e.insert(0, dns_list)

        ntp = svc.get("ntp") or {}
        self.clock_tz_e.delete(0, "end")
        self.clock_tz_e.insert(0, svc.get("clock_timezone", "") or "")
        self.clock_summer_e.delete(0, "end")
        self.clock_summer_e.insert(0, svc.get("clock_summer_time", "") or "")
        self.ntp_text.delete("1.0", "end")
        self.ntp_text.insert("1.0", _ntp_commands_for_edit(ntp))
        if hasattr(self.ntp_text, "_autosize"):
            self.ntp_text._autosize()

        self.vlans_text.delete("1.0", "end")
        self.vlans_text.insert("1.0", p.get("vlan_definitions", ""))
        if hasattr(self.vlans_text, "_autosize"):
            self.vlans_text._autosize()
        self.allow_sw_vlans.set(bool(p.get("allow_per_switch_vlans", False)))

        self._clear_vars()
        for k, v in p.get("role_variables", {}).items():
            self._add_var((k, v))

        self._clear_pa()
        for pa in p.get("port_assignments", []):
            self._add_pa(pa)

        # Layer 3
        self.l3_enabled.set(bool(p.get("layer3", False)))
        sections = _normalize_l3_sections(p)
        for kind, grid in self.l3_profile_grids.items():
            sec = sections.get(kind, {})
            grid.enabled.set(bool(sec.get("enabled")))
            grid.populate(sec.get("entries") or [])

        self._clear_svis()
        for svi in p.get("svis", []) or []:
            self._add_svi(svi)

        self.ospf_text.delete("1.0", "end")
        self.ospf_text.insert("1.0", _ospf_config_for_edit(p))
        if hasattr(self.ospf_text, "_autosize"):
            self.ospf_text._autosize()

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
        names = self.app._visible_base_set_names()
        self.base_set_cb["values"] = names
        if cur and cur not in names:
            self.base_set_cb.set("")

    def _new(self):
        self.lb.clear_selection()
        self.name_e.delete(0, "end")
        self.domain_e.delete(0, "end")
        self.mgmt_vlan_e.delete(0, "end")
        self.base_set_cb["values"] = self.app._visible_base_set_names()
        self.base_set_cb.set("")
        for w in (self.cred_enable_e,
                  self.dns_servers_e, self.clock_tz_e, self.clock_summer_e):
            w.delete(0, "end")
        self.ntp_text.delete("1.0", "end")
        if hasattr(self.ntp_text, "_autosize"):
            self.ntp_text._autosize()
        self._clear_users()
        self.vlans_text.delete("1.0", "end")
        if hasattr(self.vlans_text, "_autosize"):
            self.vlans_text._autosize()
        self.allow_sw_vlans.set(False)
        self._clear_vars(); self._clear_pa()
        # Layer 3 defaults for a new profile
        self.l3_enabled.set(False)
        for grid in self.l3_profile_grids.values():
            grid.enabled.set(False)
            grid.clear()
        self._clear_svis()
        self.ospf_text.delete("1.0", "end")
        if hasattr(self.ospf_text, "_autosize"):
            self.ospf_text._autosize()
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
        users = []
        for r in self.user_rows:
            uname = r["name"].get().strip()
            if not uname:
                continue
            pw = r["pw"].get().strip()
            priv_raw = r["priv"].get().strip()
            try:
                priv = int(priv_raw) if priv_raw else 15
            except ValueError:
                priv = 15
            users.append({"name": uname, "password": pw, "privilege": priv})
        if users:
            credentials["users"] = users
        if self.cred_enable_e.get().strip():
            credentials["enable_secret"] = self.cred_enable_e.get().strip()

        dns_servers = [s.strip() for s in self.dns_servers_e.get().split(",")
                       if s.strip()]
        services = {}
        if dns_servers:
            services["dns_servers"] = dns_servers
        ntp_cmds = self.ntp_text.get("1.0", "end").strip()
        if ntp_cmds:
            services["ntp"] = {"commands": ntp_cmds}
        if self.clock_tz_e.get().strip():
            services["clock_timezone"] = self.clock_tz_e.get().strip()
        if self.clock_summer_e.get().strip():
            services["clock_summer_time"] = self.clock_summer_e.get().strip()

        data = {
            "domain_name":      self.domain_e.get().strip(),
            "mgmt_vlan":        self.mgmt_vlan_e.get().strip(),
            "base_set":         self.base_set_cb.get().strip(),
            "vlan_definitions": self.vlans_text.get("1.0", "end").strip(),
            "allow_per_switch_vlans": bool(self.allow_sw_vlans.get()),
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
                kind: {
                    "enabled": bool(grid.enabled.get()),
                    "entries": grid.collect_profile_entries(),
                }
                for kind, grid in self.l3_profile_grids.items()
            }
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
            ospf_cfg = self.ospf_text.get("1.0", "end").strip()
            if ospf_cfg:
                data["ospf_config"] = ospf_cfg
            bgp_instances = self._collect_bgp_instances()
            if bgp_instances:
                data["bgp"] = {"instances": bgp_instances}
            acls = self._collect_acls()
            if acls:
                data["acls"] = acls

        self.app.profiles[name] = data
        save_json("profiles.json", self.app.profiles)
        self._refresh()
        if name in self.app.profiles:
            self.lb.select(name)
        self.app.gen_tab.refresh_combos()
        _dialog("Saved", f"Profile '{name}' saved.")


