"""L3 section normalization and legacy profile migration."""

def _normalize_l3_sections(profile):
    """Return the profile's l3_sections dict, building it from a legacy
    `mgmt_style` value when missing. Layer 3 profiles emit Loopback0,
    Routed Mgmt Interface, and Mgmt SVI sections independently based on
    their `enabled` flags. Returned dict is a fresh copy - callers can
    use it for reads but should write through to profile["l3_sections"]
    explicitly if persisting back."""
    sections = profile.get("l3_sections")
    if isinstance(sections, dict) and sections:
        # Fill in missing keys so callers can read without guarding.
        out = {
            "loopback":    {"enabled": False, "ip": "", "mask": "255.255.255.255",
                            "description": "Switch MGMT / Router-ID"},
            "routed_mgmt": {"enabled": False, "interface": "", "ip": "",
                            "mask": "", "description": "Routed Mgmt Uplink"},
            "mgmt_svi":    {"enabled": False, "vlan": "", "ip": "", "mask": "",
                            "description": "Switch MGMT"},
        }
        for k, defaults in out.items():
            block = sections.get(k) or {}
            merged = dict(defaults)
            merged.update({kk: vv for kk, vv in block.items() if vv is not None})
            out[k] = merged
        # Legacy migration: the standalone default_routed_mask field has
        # been removed in favour of the Routed Interface section's mask.
        # Honor the old value when the new field is blank so existing
        # profiles still pre-fill Step 3 correctly until they're re-saved.
        legacy_drm = (profile.get("default_routed_mask") or "").strip()
        if legacy_drm and not (out["routed_mgmt"].get("mask") or "").strip():
            out["routed_mgmt"]["mask"] = legacy_drm
        return _enrich_l3_sections(out)
    # Migrate from legacy mgmt_style.
    style = (profile.get("mgmt_style") or "svi").strip().lower()
    mgmt_vlan = str(profile.get("mgmt_vlan") or "").strip()
    return _enrich_l3_sections({
        "loopback": {
            "enabled":     style == "loopback",
            "ip":          "",
            "mask":        "255.255.255.255",
            "description": "Switch MGMT / Router-ID",
        },
        "routed_mgmt": {
            "enabled":     style == "routed_uplink",
            "interface":   "",
            "ip":          "",
            "mask":        "",
            "description": "Routed Mgmt Uplink",
        },
        "mgmt_svi": {
            "enabled":     style == "svi",
            "vlan":        mgmt_vlan,
            "ip":          "",
            "mask":        "",
            "description": "Switch MGMT",
        },
    })


_L3_LOOPBACK_DEFAULTS = {
    "number": "0", "ip": "", "mask": "255.255.255.255",
    "description": "Switch MGMT / Router-ID", "commands": "",
}
_L3_LOOPBACK_COMMANDS_DEFAULT = (
    "description //{{ description }}\n"
    "ip address {{ ip }} {{ mask }}\n"
    "no shutdown"
)
_L3_ROUTED_MGMT_DEFAULTS = {
    "interface": "", "ip": "", "mask": "", "description": "Routed Mgmt Uplink",
}
_L3_MGMT_SVI_DEFAULTS = {
    "vlan": "", "ip": "", "mask": "", "description": "Switch MGMT",
}

def _l3_section_entries(section, field_defaults):
    """Normalize an l3_sections block to a list of entry dicts."""
    if not isinstance(section, dict):
        return []
    entries = section.get("entries")
    if isinstance(entries, list):
        out = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            entry = dict(field_defaults)
            entry.update({k: v for k, v in raw.items() if v is not None})
            out.append(entry)
        if out:
            return out
    legacy = dict(field_defaults)
    for k in field_defaults:
        if k in section and section[k] is not None:
            legacy[k] = section[k]
    if section.get("enabled") or any(str(legacy.get(k) or "").strip()
                                   for k in field_defaults):
        return [legacy]
    return []


def _enrich_l3_sections(sections):
    """Attach normalized `entries` lists to each l3_sections block."""
    if not isinstance(sections, dict):
        return {}
    out = dict(sections)
    out["loopback"] = dict(sections.get("loopback") or {})
    out["routed_mgmt"] = dict(sections.get("routed_mgmt") or {})
    out["mgmt_svi"] = dict(sections.get("mgmt_svi") or {})
    out["loopback"]["entries"] = _l3_section_entries(
        out["loopback"], _L3_LOOPBACK_DEFAULTS)
    out["routed_mgmt"]["entries"] = _l3_section_entries(
        out["routed_mgmt"], _L3_ROUTED_MGMT_DEFAULTS)
    out["mgmt_svi"]["entries"] = _l3_section_entries(
        out["mgmt_svi"], _L3_MGMT_SVI_DEFAULTS)
    return out
