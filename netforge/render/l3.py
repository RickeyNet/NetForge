"""L3 lookup, VLAN remap, OSPF edit helpers, and port assignment expansion."""

import re

from netforge.data.iface import _canon_iface, expand_range_iface
from netforge.render.normalize import (
    _L3_LOOPBACK_DEFAULTS,
    _L3_MGMT_SVI_DEFAULTS,
    _L3_ROUTED_MGMT_DEFAULTS,
    _enrich_l3_sections,
    _normalize_l3_sections,
)

def _assigned_port_names(port_assignments, roles=None, requires_ip_only=False):
    """Expand Step 2 / profile port assignments into individual interfaces.

    Skips blank roles and explicit 'unassigned'. When *requires_ip_only* is
    True, only ports mapped to a role with requires_ip=True are returned.
    """
    names = set()
    for pa in port_assignments or []:
        role_name = pa.get("role")
        if not role_name or role_name == "unassigned":
            continue
        if requires_ip_only:
            role = (roles or {}).get(role_name, {}) or {}
            if not role.get("requires_ip"):
                continue
        for iface in expand_range_iface(pa.get("interfaces", "")):
            iface = iface.strip()
            if iface:
                names.add(iface)
    return names


def _expand_assigned_ifaces(iface_str):
    """Return canonical interface names covered by an assignment string."""
    s = (iface_str or "").strip()
    if not s:
        return []
    return [_canon_iface(i) for i in expand_range_iface(s)]


def _find_routed_mgmt_entry(iface_name, rm_entries):
    """Match a Step 2 assignment to a profile routed_mgmt entry."""
    assigned = set(_expand_assigned_ifaces(iface_name))
    if not assigned:
        return {}
    blank_entry = None
    for entry in rm_entries or []:
        if not isinstance(entry, dict):
            continue
        rm_name = (entry.get("interface") or "").strip()
        if not rm_name:
            blank_entry = entry
            continue
        if assigned & set(_expand_assigned_ifaces(rm_name)):
            return entry
    if blank_entry is not None and len(rm_entries) == 1:
        return blank_entry
    return {}


def _find_sw_routed_mgmt(iface_name, sw):
    """Match a Step 2 assignment to per-switch routed_mgmt overrides."""
    assigned = set(_expand_assigned_ifaces(iface_name))
    sw_rms = _sw_routed_mgmt_map(sw)
    for iface in assigned:
        if iface in sw_rms:
            return sw_rms[iface]
    for item in sw.get("routed_mgmt_interfaces") or []:
        if not isinstance(item, dict):
            continue
        if assigned & set(_expand_assigned_ifaces(item.get("interface") or "")):
            return item
    items = [i for i in (sw.get("routed_mgmt_interfaces") or [])
             if isinstance(i, dict)]
    if len(items) == 1 and not str(items[0].get("interface") or "").strip():
        return items[0]
    return sw_rms.get("", {})


def _lookup_routed_iface_ips(routed_iface_ips, iface_name):
    """Look up Step 3 routed IP/mask rows, tolerating range vs single-port keys."""
    canon = _canon_iface(iface_name)
    info = (routed_iface_ips or {}).get(canon, {}) or {}
    if info.get("ip") or info.get("mask"):
        return info
    assigned = set(_expand_assigned_ifaces(iface_name))
    for key, val in (routed_iface_ips or {}).items():
        if assigned & set(_expand_assigned_ifaces(key)):
            return val or {}
    return {}


def _routed_mgmt_covered_by_role(rm_if, pa_list, roles):
    """True when a requires_ip role assignment already covers this iface."""
    rm_ports = set(_expand_assigned_ifaces(rm_if))
    if not rm_ports:
        return False
    for pa in pa_list or []:
        role_name = pa.get("role")
        if not role_name or role_name == "unassigned":
            continue
        if not (roles.get(role_name, {}) or {}).get("requires_ip"):
            continue
        if rm_ports & set(_expand_assigned_ifaces(pa.get("interfaces", ""))):
            return True
    return False


def _sw_loopbacks_map(sw):
    result = {}
    for item in sw.get("loopbacks") or []:
        if isinstance(item, dict):
            num = str(item.get("number") or "").strip()
            if num:
                result[num] = item
    if "0" not in result and any((sw.get(k) or "").strip()
                                  for k in ("loopback0_ip", "loopback0_desc")):
        result["0"] = {
            "number": "0",
            "ip": sw.get("loopback0_ip", ""),
            "mask": sw.get("loopback0_mask", ""),
            "description": sw.get("loopback0_desc", ""),
        }
    return result


def _sw_routed_mgmt_map(sw):
    result = {}
    for item in sw.get("routed_mgmt_interfaces") or []:
        if isinstance(item, dict):
            iface = _canon_iface(item.get("interface") or "")
            if iface:
                result[iface] = item
    legacy_ip = (sw.get("routed_mgmt_ip") or "").strip()
    legacy_mask = (sw.get("routed_mgmt_mask") or "").strip()
    if legacy_ip or legacy_mask:
        result.setdefault("", {
            "interface": "",
            "ip": legacy_ip,
            "mask": legacy_mask,
        })
    return result


def _sw_mgmt_svis_map(sw):
    result = {}
    for item in sw.get("mgmt_svis") or []:
        if isinstance(item, dict):
            vlan = str(item.get("vlan") or "").strip()
            if vlan:
                result[vlan] = item
    legacy_vlan = (sw.get("mgmt_svi_vlan") or "").strip()
    legacy_ip = (sw.get("mgmt_svi_ip") or sw.get("mgmt_ip") or "").strip()
    legacy_mask = (sw.get("mgmt_svi_mask") or sw.get("mgmt_mask") or "").strip()
    if legacy_vlan or legacy_ip or legacy_mask:
        result.setdefault(legacy_vlan or "", {
            "vlan": legacy_vlan,
            "ip": legacy_ip,
            "mask": legacy_mask,
        })
    return result


def _first_loopback_ip(sw, l3_sections):
    lb_sec = l3_sections.get("loopback", {}) or {}
    if lb_sec.get("enabled"):
        sw_map = _sw_loopbacks_map(sw)
        for entry in lb_sec.get("entries") or []:
            num = str(entry.get("number") or "0").strip() or "0"
            sw_lb = sw_map.get(num, {})
            ip = (sw_lb.get("ip") or entry.get("ip") or "").strip()
            if ip:
                return ip
    return (sw.get("loopback0_ip") or "").strip()


def _legacy_ospf_to_config(ospf):
    """Convert the old structured ospf dict into IOS lines for editing."""
    if not isinstance(ospf, dict) or not ospf.get("enabled"):
        return ""
    pid = (str(ospf.get("process_id") or "1")).strip() or "1"
    lines = [f"router ospf {pid}"]
    passive_default = bool(ospf.get("passive_default"))
    passive_ifaces = ospf.get("passive_interfaces") or []
    if passive_default:
        lines.append("passive-interface default")
        for pi in passive_ifaces:
            pi = str(pi).strip()
            if pi:
                lines.append(f"no passive-interface {pi}")
    else:
        for pi in passive_ifaces:
            pi = str(pi).strip()
            if pi:
                lines.append(f"passive-interface {pi}")
    for n in ospf.get("networks") or []:
        if not isinstance(n, dict):
            continue
        net = (n.get("network") or "").strip()
        wc = (n.get("wildcard") or "").strip()
        area = (str(n.get("area") or "0")).strip() or "0"
        if net and wc:
            lines.append(f"network {net} {wc} area {area}")
    lines.append("exit")
    return "\n".join(lines)


def _ospf_config_for_edit(profile):
    raw = profile.get("ospf_config")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _legacy_ospf_to_config(profile.get("ospf") or {})


def _profile_has_ospf(profile):
    return bool(_ospf_config_for_edit(profile).strip())


def _ospf_process_id(profile):
    for line in _ospf_config_for_edit(profile).splitlines():
        m = re.match(r"router\s+ospf\s+(\S+)", line.strip(), re.I)
        if m:
            return m.group(1)
    ospf = profile.get("ospf") or {}
    if isinstance(ospf, dict) and ospf.get("enabled"):
        return (str(ospf.get("process_id") or "1")).strip() or "1"
    return None


def _inject_ospf_router_id(raw, sw, l3_sections):
    """Insert per-switch router-id after 'router ospf' when not already set."""
    rid = ((sw.get("router_id") or "").strip()
           or _first_loopback_ip(sw, l3_sections))
    if not rid:
        return raw.strip()
    lines = raw.splitlines()
    if any(re.match(r"router-id\s+", ln.strip(), re.I) for ln in lines):
        return raw.strip()
    out = []
    injected = False
    for line in lines:
        out.append(line)
        if not injected and re.match(r"router\s+ospf\s+", line.strip(), re.I):
            out.append(f"router-id {rid}")
            injected = True
    return "\n".join(out).strip()

_IFACE_VLAN_HEAD_RE = re.compile(
    r'^\s*interface\s+(?:Vlan|vlan)\s*(\d+)\s*$', re.I | re.M)


def _split_vlan_definitions(text):
    """Split vlan_definitions IOS into L2 VLAN stanzas and embedded
    interface-Vlan SVI stanzas. Embedded SVIs render under L3 Interfaces
    instead of the VLAN section."""
    text = (text or "").strip()
    if not text:
        return "", []
    vlan_parts = []
    embedded = []
    for block in re.split(r'\n\s*\n', text):
        block = block.strip()
        if not block:
            continue
        m = _IFACE_VLAN_HEAD_RE.match(block)
        if m:
            embedded.append({"vlan": m.group(1), "text": block})
        else:
            vlan_parts.append(block)
    return "\n\n".join(vlan_parts), embedded


def _parse_vlan_names(text):
    """Parse vlan/name pairs from IOS vlan-definition blocks.

    Returns (by_id, by_name) where by_id maps vlan ID -> lowercased name
    and by_name maps lowercased name -> vlan ID.
    """
    by_id = {}
    by_name = {}
    current_id = None
    for line in (text or "").splitlines():
        line = line.strip()
        m = re.match(r"^vlan\s+(\d+)", line, re.I)
        if m:
            current_id = m.group(1)
            continue
        m = re.match(r"^name\s+(.+)", line, re.I)
        if m and current_id:
            name = m.group(1).strip().lower()
            by_id[current_id] = name
            by_name[name] = current_id
            current_id = None
    return by_id, by_name


def _vlan_id_remap(profile, sw):
    """Map profile VLAN IDs to per-switch IDs for this switch.

    Sources (merged): vlan-definition `name` lines, Step 3 SVI rows, and
    Step 3 management-VLAN rows.
    """
    if not profile.get("allow_per_switch_vlans"):
        return {}
    remap = {}
    prof_by_id, _ = _parse_vlan_names(profile.get("vlan_definitions", ""))
    sw_text = (sw.get("vlan_definitions") or "").strip()
    if sw_text:
        _, sw_by_name = _parse_vlan_names(sw_text)
        for prof_id, name in prof_by_id.items():
            sw_id = sw_by_name.get(name)
            if sw_id and sw_id != prof_id:
                remap[prof_id] = sw_id

    for i, psvi in enumerate(profile.get("svis") or []):
        old_id = str(psvi.get("vlan") or "").strip()
        if not old_id:
            continue
        new_id = old_id
        sw_svis = sw.get("svis") or []
        if i < len(sw_svis) and isinstance(sw_svis[i], dict):
            new_id = str(sw_svis[i].get("vlan") or "").strip() or old_id
        if new_id != old_id:
            remap[old_id] = new_id

    if profile.get("layer3"):
        sections = _normalize_l3_sections(profile)
        mgmt_entries = (sections.get("mgmt_svi") or {}).get("entries") or []
        sw_msvi = sw.get("mgmt_svis") or []
        for i, entry in enumerate(mgmt_entries):
            old_id = str(entry.get("vlan") or "").strip()
            if not old_id:
                continue
            new_id = old_id
            if i < len(sw_msvi) and isinstance(sw_msvi[i], dict):
                new_id = str(sw_msvi[i].get("vlan") or "").strip() or old_id
            if new_id != old_id:
                remap[old_id] = new_id

    return remap


def _role_variables_for_switch(profile, sw):
    """Apply per-switch VLAN overrides to profile role_variables values.

    Role templates often reference VLAN IDs via keys like ``user_vlan``.
    When Step 3 changes VLAN numbers, remap any variable whose value matches
    an overridden profile VLAN ID, and refresh ``*_vlan`` keys from matching
    vlan ``name`` lines in the per-switch definitions block.
    """
    role_vars = dict(profile.get("role_variables", {}) or {})
    if not profile.get("allow_per_switch_vlans"):
        return role_vars

    remap = _vlan_id_remap(profile, sw)
    for key, val in list(role_vars.items()):
        sval = str(val).strip()
        if sval in remap:
            role_vars[key] = remap[sval]

    _, prof_by_name = _parse_vlan_names(profile.get("vlan_definitions", ""))
    sw_text = (sw.get("vlan_definitions") or "").strip()
    if not sw_text:
        return role_vars
    _, sw_by_name = _parse_vlan_names(sw_text)
    for key in profile.get("role_variables", {}) or {}:
        m = re.match(r"^(.+?)_?vlan$", key, re.I)
        if not m:
            continue
        token = re.sub(r"[_\s]+", "", m.group(1)).lower()
        if not token:
            continue
        for name in prof_by_name:
            norm_name = re.sub(r"[_\s]+", "", name).lower()
            if token in norm_name or norm_name in token:
                prof_id = prof_by_name[name]
                sw_id = sw_by_name.get(name)
                if sw_id and sw_id != prof_id:
                    role_vars[key] = sw_id
                break

    return role_vars


def _remap_svi_ips(svi_ips, remap):
    out = dict(svi_ips or {})
    if not remap:
        return out
    for old_id, new_id in remap.items():
        if old_id in out and new_id not in out:
            out[new_id] = out.pop(old_id)
    return out


def _apply_vlan_remap_to_svi(svi, remap):
    svi = dict(svi)
    vid = str(svi.get("vlan") or "").strip()
    if vid in remap:
        svi["vlan"] = remap[vid]
    return svi


def _remap_embedded_svi_text(text, old_vlan, new_vlan):
    if not text or old_vlan == new_vlan:
        return text
    return re.sub(
        r"^\s*interface\s+(?:Vlan|vlan)\s*\d+\s*$",
        f"interface Vlan{new_vlan}",
        text,
        count=1,
        flags=re.I | re.M,
    )


def _effective_svis(profile, sw):
    """Return the SVI list to render for this switch. When the profile
    allows per-switch VLAN overrides and Step 3 supplied SVI rows, those
    replace profile['svis'] so VLAN IDs stay in sync with overrides."""
    profile_svis = profile.get("svis", []) or []
    remap = _vlan_id_remap(profile, sw)

    if profile.get("allow_per_switch_vlans"):
        sw_svis = sw.get("svis")
        if isinstance(sw_svis, list) and sw_svis:
            return sw_svis

    if not profile_svis:
        return []

    out = []
    sw_svis = sw.get("svis") or []
    for i, svi in enumerate(profile_svis):
        entry = dict(svi)
        if i < len(sw_svis) and isinstance(sw_svis[i], dict):
            sw_row = sw_svis[i]
            for key in ("vlan", "description", "ip", "mask", "helper_addresses"):
                val = sw_row.get(key)
                if val not in (None, ""):
                    entry[key] = val
        entry = _apply_vlan_remap_to_svi(entry, remap)
        out.append(entry)
    return out


