"""Load and migrate base-settings JSON."""

from netforge.data.storage import load_json

# Old-key -> new-key migration for base settings.
_BASE_KEY_MIGRATION = [
    ("services_functions", ["global_services"]),
    ("aaa_radius",         ["aaa"]),
    ("vty_config",         ["line_config"]),
    ("misc",               ["security", "switching"]),
]

# Legacy keys dropped on load without folding their content elsewhere.
_BASE_LEGACY_DROP_KEYS = (
    "mgmt_port",
    "management", "ip_routes", "acl", "vlan_config", "ntp", "snmpv3",
)


def _migrate_base_set(entry):
    """In-place migrate one base-set dict from the legacy 9-section layout
    to the spreadsheet-aligned layout.  Old keys are removed after their
    content has been folded into the new keys.  When an old key has the
    same name as its new destination (e.g. 'ssh' -> 'ssh') it is kept,
    not popped, so its value survives.  Keys in _BASE_LEGACY_DROP_KEYS
    are removed unconditionally with their content discarded.  Re-running
    the migration is a no-op."""
    if not isinstance(entry, dict):
        return
    for new_key, old_keys in _BASE_KEY_MIGRATION:
        sources = [k for k in old_keys if k != new_key]
        existing = (entry.get(new_key) or "").strip()
        pieces = []
        if existing:
            pieces.append(existing)
        for ok in sources:
            val = entry.get(ok)
            if isinstance(val, str) and val.strip():
                pieces.append(val.strip())
        if pieces:
            entry[new_key] = "\n\n".join(pieces)
        for ok in sources:
            entry.pop(ok, None)
    for key in _BASE_LEGACY_DROP_KEYS:
        entry.pop(key, None)


def load_base_settings():
    """Load base_settings.json and normalize to the multi-base shape:
        {"sets": {<name>: {...}, ...}, "default": <name>}
    Legacy flat dicts are migrated into a single entry named "Base".
    Old per-entry section keys are migrated to the new spreadsheet
    category layout on load."""
    raw = load_json("base_settings.json", {})
    if isinstance(raw, dict) and isinstance(raw.get("sets"), dict):
        sets = {k: v for k, v in raw["sets"].items() if isinstance(v, dict)}
        if not sets:
            sets = {"Base": {}}
        default = raw.get("default") if raw.get("default") in sets \
            else next(iter(sets))
        for entry in sets.values():
            _migrate_base_set(entry)
        return {"sets": sets, "default": default}
    # Legacy flat shape (or empty) - wrap as a single "Base" entry.
    flat = raw if isinstance(raw, dict) else {}
    _migrate_base_set(flat)
    return {"sets": {"Base": flat}, "default": "Base"}


def resolve_base(base_root, name=None):
    """Return the base-settings dict matching *name*, falling back to the
    default entry when the name is missing or unknown."""
    sets = (base_root or {}).get("sets") or {}
    if name and name in sets:
        return sets[name]
    default = (base_root or {}).get("default")
    if default and default in sets:
        return sets[default]
    if sets:
        return next(iter(sets.values()))
    return {}
