"""Individual config block renderers (NTP, ACL, L3, BGP, SVI)."""

import re

from netforge.data.iface import _canon_iface, expand_range_iface
from netforge.render.l3 import (
    _expand_assigned_ifaces,
    _find_routed_mgmt_entry,
    _find_sw_routed_mgmt,
    _first_loopback_ip,
    _inject_ospf_router_id,
    _lookup_routed_iface_ips,
    _ospf_config_for_edit,
    _routed_mgmt_covered_by_role,
    _sw_loopbacks_map,
    _sw_mgmt_svis_map,
    _sw_routed_mgmt_map,
    _vlan_id_remap,
)
from netforge.render.normalize import (
    _L3_LOOPBACK_COMMANDS_DEFAULT,
    _L3_LOOPBACK_DEFAULTS,
    _L3_MGMT_SVI_DEFAULTS,
    _L3_ROUTED_MGMT_DEFAULTS,
    _normalize_l3_sections,
)

def _render_ntp_block(ntp):
    """Return the NTP commands to inject in the Global section.

    Profiles authored against the new free-form editor store the block
    under `services.ntp.commands` and we just emit it verbatim.  Profiles
    saved by older versions store a structured dict (servers / source_
    interface / auth_key_id / auth_key / access_group_acl / access_group_
    peers); render those into IOS commands the same way the editor used
    to, so legacy profiles keep generating identical output until the
    user opens and re-saves them."""
    if not isinstance(ntp, dict):
        return ""
    commands = (ntp.get("commands") or "").strip()
    if commands:
        return commands

    ntp_servers = ntp.get("servers") or []
    if isinstance(ntp_servers, str):
        ntp_servers = [s.strip() for s in ntp_servers.split(",") if s.strip()]
    if not ntp_servers:
        return ""
    lines = []
    source = (ntp.get("source_interface") or "").strip()
    if source:
        lines.append(f"ntp source {source}")
    key_id = (ntp.get("auth_key_id") or "").strip()
    key = (ntp.get("auth_key") or "").strip()
    if key_id and key:
        lines.append("ntp authenticate")
        lines.append(f"ntp authentication-key {key_id} md5 {key}")
        lines.append(f"ntp trusted-key {key_id}")
    acl_num = (str(ntp.get("access_group_acl") or "")).strip()
    acl_peers = ntp.get("access_group_peers") or []
    if isinstance(acl_peers, str):
        acl_peers = [p.strip() for p in acl_peers.split(",") if p.strip()]
    if acl_num and acl_peers:
        lines.append(f"ntp access-group peer {acl_num}")
        for peer in acl_peers:
            lines.append(f"access-list {acl_num} permit host {peer}")
    for s in ntp_servers:
        if key_id and key:
            lines.append(f"ntp server {s} key {key_id}")
        else:
            lines.append(f"ntp server {s}")
    return "\n".join(lines)


def _ntp_commands_for_edit(ntp):
    """Return the NTP block as plain text to populate the profile's NTP
    editor.  New profiles store the text directly under `commands`; older
    profiles get rendered through `_render_ntp_block` so opening one
    surfaces the same lines the renderer would have emitted."""
    if not isinstance(ntp, dict):
        return ""
    if ntp.get("commands"):
        return ntp["commands"]
    return _render_ntp_block(ntp)


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
        if r.get("log_input"):
            parts.append("log-input")
        elif r.get("log"):
            parts.append("log")
        lines.append(" ".join(p for p in parts if p))
    lines.append("exit")
    return "\n".join(lines)


def _render_ospf_routing(profile, sw, l3_sections):
    raw = _ospf_config_for_edit(profile)
    if not raw:
        return ""
    return _inject_ospf_router_id(raw, sw, l3_sections)

def _substitute_loopback_commands(commands, ip, mask, description,
                                  profile_description=""):
    """Fill loopback interface-body placeholders from resolved values."""
    out = commands or ""
    for token, val in (
        ("{{ ip }}", ip),
        ("{{ mask }}", mask),
        ("{{ description }}", description),
    ):
        out = out.replace(token, val)
    desc = (description or "").strip()
    prof = (profile_description or "").strip()
    if desc and prof and prof != desc:
        out = out.replace(f"description //{prof}", f"description //{desc}")
        out = out.replace(f"description {prof}", f"description //{desc}")
    if desc:
        out, count = re.subn(
            r"^description\s+\S.*$",
            f"description //{desc}",
            out,
            count=1,
            flags=re.I | re.M,
        )
        if not count and desc not in out:
            out = f"description //{desc}\n{out}"
    return out.strip()


def _loopback_description(entry, sw_lb):
    """Prefer per-switch Step 3 description over profile defaults."""
    profile_desc = (entry.get("description") or "Switch MGMT / Router-ID").strip()
    if not sw_lb:
        return profile_desc
    if "description" not in sw_lb:
        return profile_desc
    sw_desc = (sw_lb.get("description") or "").strip()
    return sw_desc or profile_desc


def _render_l3_loopbacks(l3, lb_sec, sw):
    if not lb_sec.get("enabled"):
        return
    sw_lbs = _sw_loopbacks_map(sw)
    for entry in lb_sec.get("entries") or []:
        number = str(entry.get("number") or "0").strip() or "0"
        sw_lb = sw_lbs.get(number, {})
        lb_ip = (sw_lb.get("ip") or entry.get("ip") or "").strip()
        lb_mask = (sw_lb.get("mask") or entry.get("mask")
                   or "255.255.255.255").strip()
        lb_desc = _loopback_description(entry, sw_lb)
        profile_desc = (entry.get("description") or "Switch MGMT / Router-ID").strip()
        commands = (entry.get("commands") or "").strip()
        if commands:
            body = _substitute_loopback_commands(
                commands, lb_ip, lb_mask, lb_desc, profile_desc)
        elif lb_ip:
            body = (
                f"description //{lb_desc}\n"
                f"ip address {lb_ip} {lb_mask}\n"
                f"no shutdown"
            )
        else:
            body = ""
        if body:
            l3.append(
                f"interface Loopback{number}\n"
                f"{body}\n"
                f"exit"
            )


def _render_l3_routed_mgmt(l3, rm_sec, sw, profile, roles):
    if not rm_sec.get("enabled"):
        return
    pa_list = profile.get("port_assignments", []) or []
    sw_rms = _sw_routed_mgmt_map(sw)
    for entry in rm_sec.get("entries") or []:
        rm_if = (entry.get("interface") or "").strip()
        if rm_if and _routed_mgmt_covered_by_role(rm_if, pa_list, roles):
            continue
        sw_rm = _find_sw_routed_mgmt(rm_if, sw) if rm_if else sw_rms.get("", {})
        if not sw_rm and rm_if:
            sw_rm = sw_rms.get(_canon_iface(rm_if), sw_rms.get("", {}))
        rm_ip = (sw_rm.get("ip") or entry.get("ip") or "").strip()
        if not rm_ip:
            rm_ip = (sw.get("routed_mgmt_ip") or "").strip()
        rm_mask = (sw_rm.get("mask") or entry.get("mask") or "").strip()
        if not rm_mask:
            rm_mask = (sw.get("routed_mgmt_mask") or "").strip()
        rm_desc = (entry.get("description") or "Routed Mgmt Uplink").strip()
        if rm_if and rm_ip and rm_mask:
            l3.append(
                f"interface {rm_if}\n"
                f"description //{rm_desc}\n"
                f"no switchport\n"
                f"ip address {rm_ip} {rm_mask}\n"
                f"no shutdown\n"
                f"exit"
            )


def _render_l3_mgmt_svis(mgmt, svi_sec, sw, profile):
    if not svi_sec.get("enabled"):
        return
    sw_msvi_list = [
        item for item in (sw.get("mgmt_svis") or [])
        if isinstance(item, dict)
    ]
    sw_msvi_by_vlan = _sw_mgmt_svis_map(sw)
    remap = _vlan_id_remap(profile, sw)
    mgmt_entries = svi_sec.get("entries") or []
    for i, entry in enumerate(mgmt_entries):
        profile_vlan = str(entry.get("vlan") or "").strip()
        sw_entry = {}
        if i < len(sw_msvi_list):
            sw_entry = sw_msvi_list[i]
        elif profile_vlan in sw_msvi_by_vlan:
            sw_entry = sw_msvi_by_vlan[profile_vlan]
        elif len(mgmt_entries) == 1 and len(sw_msvi_list) == 1:
            sw_entry = sw_msvi_list[0]
        mgmt_vlan = (sw_entry.get("vlan") or "").strip()
        if not mgmt_vlan:
            mgmt_vlan = remap.get(profile_vlan, profile_vlan)
        if not mgmt_vlan:
            mgmt_vlan = str(profile.get("mgmt_vlan") or "1").strip() or "1"
        svi_ip = (sw_entry.get("ip") or entry.get("ip") or "").strip()
        if not svi_ip and len(mgmt_entries) == 1:
            svi_ip = (sw.get("mgmt_svi_ip") or sw.get("mgmt_ip") or "").strip()
        svi_mask = (sw_entry.get("mask") or entry.get("mask") or "").strip()
        if not svi_mask and len(mgmt_entries) == 1:
            svi_mask = (sw.get("mgmt_svi_mask")
                        or sw.get("mgmt_mask") or "").strip()
        svi_desc = (sw_entry.get("description")
                    or entry.get("description") or "Switch MGMT").strip()
        if svi_ip and svi_mask:
            mgmt.append(
                f"interface vlan{mgmt_vlan}\n"
                f"description {svi_desc}\n"
                f"ip address {svi_ip} {svi_mask}\n"
                f"exit"
            )


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
        if not slots and default_peer_asn:
            slots = [{"peer_asn": default_peer_asn, "description": ""}]

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


_IFACE_VLAN_HEAD_RE = re.compile(
    r'^\s*interface\s+(?:Vlan|vlan)\s*(\d+)\s*$', re.I | re.M)


def _render_svi_block(svi, svi_ips):
    """Build one interface Vlan stanza from a structured SVI dict."""
    vlan = (svi.get("vlan") or "").strip()
    if not vlan:
        return ""
    per_sw = (svi_ips or {}).get(vlan, {}) or {}
    ip = (per_sw.get("ip") or svi.get("ip") or "").strip()
    mask = (per_sw.get("mask") or svi.get("mask") or "").strip()
    desc = (per_sw.get("description") or svi.get("description")
            or svi.get("name") or "").strip()
    helpers_raw = svi.get("helper_addresses") or ""
    if isinstance(helpers_raw, list):
        helpers = [h.strip() for h in helpers_raw if str(h).strip()]
    else:
        helpers = [h.strip() for h in str(helpers_raw).split(",") if h.strip()]
    lines = [f"interface Vlan{vlan}"]
    if desc:
        lines.append(f"description {desc}")
    if ip and mask:
        lines.append(f"ip address {ip} {mask}")
    else:
        lines.append("no ip address")
    for h in helpers:
        lines.append(f"ip helper-address {h}")
    lines.append("no shutdown")
    lines.append("exit")
    return "\n".join(lines)

