"""Config orchestrators: section dict and full IOS string."""

from jinja2.sandbox import SandboxedEnvironment

from netforge.data.iface import _canon_iface, expand_port_groups_for_stack
from netforge.render.l3 import (
    _assigned_port_names,
    _effective_svis,
    _find_routed_mgmt_entry,
    _find_sw_routed_mgmt,
    _lookup_routed_iface_ips,
    _ospf_process_id,
    _profile_has_ospf,
    _remap_embedded_svi_text,
    _remap_svi_ips,
    _role_variables_for_switch,
    _split_vlan_definitions,
    _vlan_id_remap,
)
from netforge.render.normalize import _normalize_l3_sections
from netforge.render.sections import (
    _render_acl,
    _render_bgp,
    _render_l3_loopbacks,
    _render_l3_mgmt_svis,
    _render_l3_routed_mgmt,
    _render_ntp_block,
    _render_ospf_routing,
    _render_svi_block,
)

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
    # SandboxedEnvironment: role/profile command templates come from
    # user-editable JSON (and can be replaced via Import Settings), so
    # block attribute access that would allow Jinja SSTI -> code execution.
    env = SandboxedEnvironment()
    role_vars = _role_variables_for_switch(profile, sw)
    stack = model.get("stack_members", 1)
    layer3 = bool(profile.get("layer3", False))

    def _r(text):
        try:
            return env.from_string(text).render(**role_vars)
        except Exception:
            return text

    # Per-port IPs entered in Generate Config Step 3 for ports assigned
    # to a role with requires_ip=True. Keyed by interface name. We
    # canonicalize keys (strip + lowercase the "range " token) so a
    # lookup tolerates trivial differences between what Step-2 stored
    # and what Step-3 used as the dict key.
    raw_routed = sw.get("routed_iface_ips", {}) or {}
    routed_iface_ips = {_canon_iface(k): v for k, v in raw_routed.items()}
    # Track which entries the renderer actually consumed so we can
    # surface a warning if the user typed IPs that never landed in
    # the generated config (typically a key mismatch).
    routed_iface_consumed = set()

    # Build sets of ports claimed by Step 2 assignments so the disabled-
    # port pass and standalone L3 routed blocks skip them.
    pa_list = profile.get("port_assignments", []) or []
    assigned_iface_names = _assigned_port_names(pa_list, roles)

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
    gb.append(base.get("basic_config", ""))
    gb.append(base.get("services_functions", ""))
    gb.append(f"hostname {sw['hostname']}")
    gb.append(base.get("ip_services", ""))
    gb.append(base.get("snooping", ""))
    gb.append(base.get("http_server", ""))
    gb.append(base.get("mgmt_vrf", ""))
    gb.append(base.get("logging", ""))
    gb.append(f"enable secret {sw['enable_secret']}")
    users = list(sw.get("users") or [])
    if not users:
        # Legacy single-credential path - still supported for switches
        # generated against profiles that haven't been migrated yet.
        legacy_name = (sw.get("local_username")
                       or base.get("local_username", "admin")
                       or "admin")
        users = [{"name": legacy_name,
                  "password": sw.get("admin_password", ""),
                  "privilege": 15}]
    for u in users:
        uname = (u.get("name") or "").strip()
        if not uname:
            continue
        upw = u.get("password", "") or ""
        priv = u.get("privilege", 15)
        try:
            priv = int(priv)
        except (TypeError, ValueError):
            priv = 15
        gb.append(f"username {uname} privilege {priv} secret {upw}")
    gb.append(base.get("aaa_radius", ""))
    provision = model.get("provision", "").strip()
    if provision:
        for member in range(1, stack + 1):
            gb.append(f"switch {member} provision {provision}")
    gb.append(f"ip domain name {sw['domain_name']}")
    gb.append(base.get("ssh", ""))
    gb.append(base.get("archive", ""))
    gb.append(base.get("misc", ""))

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
    ntp_block = _render_ntp_block(ntp)
    if ntp_block:
        gb.append(ntp_block)

    # ── 2  VLANs ────────────────────────────────────────────────────────
    vl = []
    # Per-switch override: if the profile allows it and Step 3 supplied a
    # non-empty block, it REPLACES the profile's VLAN definitions for
    # this one switch. Embedded interface-Vlan blocks are peeled off and
    # emitted under L3 Interfaces so SVIs stay with routing, not VLANs.
    sw_vlans = (sw.get("vlan_definitions") or "").strip()
    vlan_src = sw_vlans if sw_vlans else profile.get("vlan_definitions", "")
    if layer3:
        vlan_only, embedded_vlan_svis = _split_vlan_definitions(vlan_src)
        if vlan_only:
            vl.append(vlan_only)
    else:
        embedded_vlan_svis = []
        if vlan_src:
            vl.append(vlan_src)
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

        _render_l3_loopbacks(l3, l3_sections.get("loopback", {}), sw)
        _render_l3_routed_mgmt(l3, l3_sections.get("routed_mgmt", {}), sw,
                               profile, roles)

        svi_ips = _remap_svi_ips(sw.get("svi_ips", {}) or {},
                                 _vlan_id_remap(profile, sw))
        rendered_svi_vlans = set()
        for svi in _effective_svis(profile, sw):
            block = _render_svi_block(svi, svi_ips)
            if block:
                l3.append(block)
                rendered_svi_vlans.add((svi.get("vlan") or "").strip())

        # Embedded interface-Vlan blocks from vlan_definitions (e.g.
        # shutdown vlan1) that are not already covered by structured SVIs.
        vlan_remap = _vlan_id_remap(profile, sw)
        for emb in embedded_vlan_svis:
            vlan = emb.get("vlan", "")
            new_vlan = vlan_remap.get(vlan, vlan)
            if new_vlan and new_vlan not in rendered_svi_vlans:
                text = _remap_embedded_svi_text(
                    emb.get("text", ""), vlan, new_vlan)
                per_sw = svi_ips.get(new_vlan, {}) or svi_ips.get(vlan, {}) or {}
                ip = (per_sw.get("ip") or "").strip()
                mask = (per_sw.get("mask") or "").strip()
                if ip and mask and "ip address" not in text.lower():
                    text = text.rstrip() + f"\nip address {ip} {mask}"
                l3.append(text)
                rendered_svi_vlans.add(new_vlan)

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
            # expand the range and skip ports assigned a role in Step 2
            # (those are rendered below with their role template).
            single_ports = [
                f"{pg['prefix']}{i}"
                for i in range(pg["start"], pg["end"] + 1)
            ]
            # collapse consecutive kept ports back into ranges
            run_start = None
            run_end = None
            for i, p in zip(range(pg["start"], pg["end"] + 1), single_ports):
                if p in assigned_iface_names:
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
                ifaces.append(f"interface {iface}\n"
                              f"no ip address\nnegotiation auto\nexit")
    ospf_pid_for_iface = (
        _ospf_process_id(profile)
        if layer3 and _profile_has_ospf(profile) else None
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
            canon_iface = _canon_iface(iface_name)
            ip_info = _lookup_routed_iface_ips(routed_iface_ips, iface_name)
            if ip_info.get("ip") or ip_info.get("mask"):
                routed_iface_consumed.add(canon_iface)
            ip_val = (ip_info.get("ip") or "").strip()
            mask_val = (ip_info.get("mask") or "").strip()
            # Fall back to the Routed Interface section when Step 3's
            # per-port row left a field blank. Same priority chain the
            # standalone Routed Mgmt Interface block uses: per-switch
            # override (sw[routed_mgmt_*]) first, then the profile's
            # l3_sections.routed_mgmt defaults. Lets the user type a
            # site-wide mask on the profile and a per-switch IP into
            # Step 3's Routed Interface box, without retyping either
            # one on every routed-port row in Step 3.
            if not ip_val or not mask_val:
                rm_entries = (l3_sections.get("routed_mgmt", {})
                              or {}).get("entries") or []
                rm_fallback = _find_routed_mgmt_entry(iface_name, rm_entries)
                sw_rm = _find_sw_routed_mgmt(iface_name, sw)
                if not ip_val:
                    ip_val = ((sw_rm.get("ip") or "").strip()
                              or (sw.get("routed_mgmt_ip") or "").strip()
                              or (rm_fallback.get("ip") or "").strip())
                if not mask_val:
                    mask_val = ((sw_rm.get("mask") or "").strip()
                                or (sw.get("routed_mgmt_mask") or "").strip()
                                or (rm_fallback.get("mask") or "").strip())
            ctx["ip"] = ip_val
            ctx["mask"] = mask_val
            if ospf_pid_for_iface:
                ctx.setdefault("ospf_pid", ospf_pid_for_iface)
        try:
            rendered = env.from_string(cmds).render(**ctx)
        except Exception as exc:
            rendered = (f"! ERROR rendering role '{pa.get('role','')}': {exc}\n"
                        f"{cmds}")
        ifaces.append(f"interface {iface_name}\n{rendered}\nexit")

    # Surface routed_iface_ips entries the user typed but the renderer
    # never matched against a port_assignment. Most common cause: the
    # interface text on Step 2 was edited after the IP was typed, so
    # the saved key no longer matches the role's interface name.
    if layer3 and routed_iface_ips:
        unused = sorted(k for k in routed_iface_ips
                        if k not in routed_iface_consumed
                        and (routed_iface_ips[k].get("ip")
                             or routed_iface_ips[k].get("mask")))
        if unused:
            warn = ["! WARNING: Routed Interface IPs typed in Step 3 were "
                    "not applied to any interface."]
            warn.append("! Check that the Step 2 interface name still "
                        "matches the role assignment:")
            for k in unused:
                v = routed_iface_ips[k] or {}
                ip = (v.get("ip") or "").strip()
                mask = (v.get("mask") or "").strip()
                warn.append(f"!   {k}: ip={ip or '(empty)'} "
                            f"mask={mask or '(empty)'}")
            ifaces.insert(0, "\n".join(warn))

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
        _render_l3_mgmt_svis(mgmt, l3_sections.get("mgmt_svi", {}), sw, profile)
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
        ospf_block = _render_ospf_routing(profile, sw, l3_sections)
        if ospf_block:
            routing.append(ospf_block)

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

    # ── 6  VTY / Line Config ─────────────────────────────────────────────
    lc = [base.get("vty_config", "")]

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
