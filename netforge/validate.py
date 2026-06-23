"""Format validation for config inputs (IPv4 addresses, masks, VLAN IDs).

Pure functions shared by the Generate tab (pre-render checks) and the FTD
setup dialog (field checks) so a fat-fingered address is caught at the
desk instead of on the wire.
"""

import ipaddress

from netforge.data.iface import expand_range_iface


def is_ipv4(value):
    try:
        ipaddress.IPv4Address((value or "").strip())
        return True
    except Exception:
        return False


def is_ipv4_mask(value):
    """True for a contiguous dotted-quad netmask (e.g. 255.255.255.0)."""
    v = (value or "").strip()
    if not is_ipv4(v):
        return False
    bits = int(ipaddress.IPv4Address(v))
    inv = bits ^ 0xFFFFFFFF          # the host part must be a run of 1s
    return (inv & (inv + 1)) == 0    # ...which means inv+1 is a power of 2


def is_vlan_id(value):
    v = str(value or "").strip()
    return v.isdigit() and 1 <= int(v) <= 4094


def _csv_ips_ok(value):
    parts = [p.strip() for p in str(value or "").split(",") if p.strip()]
    return all(is_ipv4(p) for p in parts)


_CHECKS = {
    "ip":     (is_ipv4,      "IPv4 address"),
    "mask":   (is_ipv4_mask, "subnet mask"),
    "vlan":   (is_vlan_id,   "VLAN ID (1-4094)"),
    "ip_csv": (_csv_ips_ok,  "comma-separated IPv4 list"),
}


def field_errors(specs):
    """Validate ``(label, value, kind)`` triples; blank values pass.

    ``kind`` is one of 'ip', 'mask', 'vlan', 'ip_csv'. Returns a list of
    human-readable error strings for the values that failed.
    """
    errors = []
    for label, value, kind in specs:
        v = value.strip() if isinstance(value, str) else value
        if v in (None, ""):
            continue
        check, name = _CHECKS[kind]
        if not check(v):
            errors.append(f"{label}: '{v}' is not a valid {name}")
    return errors


def _duplicate_interfaces(profile):
    """Interfaces assigned to more than one role in the profile."""
    seen, dups = set(), []
    for pa in profile.get("port_assignments") or []:
        for iface in expand_range_iface(pa.get("interfaces", "") or ""):
            key = iface.strip().lower()
            if not key:
                continue
            if key in seen:
                dups.append(iface.strip())
            else:
                seen.add(key)
    return sorted(set(dups))


def validate_switch_config(model, profile, roles, base, sw):
    """Pre-render checks. Returns ``(errors, warnings)`` lists of strings.

    Errors should block generation; warnings are advisory. Only non-blank
    values are checked, so a partially filled switch is not over-flagged.
    """
    errors, warnings = [], []

    specs = [
        ("Management IP",   sw.get("mgmt_ip"),         "ip"),
        ("Management mask", sw.get("mgmt_mask"),       "mask"),
        ("Default gateway", sw.get("default_gateway"), "ip"),
        ("OOB IP",          sw.get("oob_ip"),          "ip"),
        ("OOB mask",        sw.get("oob_mask"),        "mask"),
        ("Router ID",       sw.get("router_id"),       "ip"),
    ]
    for svi in sw.get("svis") or []:
        v = svi.get("vlan")
        specs.append((f"SVI {v} VLAN", v,            "vlan"))
        specs.append((f"SVI {v} IP",   svi.get("ip"),   "ip"))
        specs.append((f"SVI {v} mask", svi.get("mask"), "mask"))
        for h in svi.get("helper_addresses") or []:
            specs.append((f"SVI {v} helper address", h, "ip"))
    for name, entry in (sw.get("routed_iface_ips") or {}).items():
        entry = entry or {}
        specs.append((f"Routed {name} IP",   entry.get("ip"),   "ip"))
        specs.append((f"Routed {name} mask", entry.get("mask"), "mask"))
    for r in sw.get("static_routes") or []:
        specs.append(("Static route network",  r.get("prefix"),   "ip"))
        specs.append(("Static route mask",     r.get("mask"),     "mask"))
        specs.append(("Static route next-hop", r.get("next_hop"), "ip"))
    for b in sw.get("bgp_instances") or []:
        specs.append(("BGP ISP gateway",       b.get("isp_gateway"),  "ip"))
        specs.append(("BGP advertised network", b.get("user_network"), "ip"))
        specs.append(("BGP advertised mask",    b.get("user_mask"),    "mask"))
        for f in b.get("peer_fills") or []:
            specs.append(("BGP peer IP", f.get("peer_ip"), "ip"))

    errors.extend(field_errors(specs))

    for iface in _duplicate_interfaces(profile):
        errors.append(
            f"Interface {iface} is assigned to more than one role")

    return errors, warnings
