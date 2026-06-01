"""Paths and JSON file I/O for the live data/ directory."""

import json
import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    # Repo root: netforge/data/storage.py -> ../../
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _BUNDLE_DIR = BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")
ICON_PATH = os.path.join(_BUNDLE_DIR, "NetForge.ico")


def merge_bundled_data():
    """Seed data/ from bundled defaults and add any new bundled entries.

    On first run, copy the whole bundled data/ folder. On every subsequent
    launch, merge any new top-level keys from bundled JSON files into the
    local files so new starter models/roles/profiles/base-sets ship with
    upgrades. User-edited entries (matching names) are never overwritten.
    """
    bundled_data = os.path.join(_BUNDLE_DIR, "data")
    if not os.path.isdir(bundled_data):
        return
    # Running from source: bundled and live data/ are the same folder.
    if os.path.isdir(DATA_DIR) and os.path.samefile(bundled_data, DATA_DIR):
        return

    if not os.path.exists(DATA_DIR):
        import shutil
        shutil.copytree(bundled_data, DATA_DIR)
        return

    # Per-file merge: top-level keys are item names; user wins on conflict.
    # base_settings.json is special - items live under "sets".
    flat_files = ("models.json", "roles.json", "profiles.json")
    for name in flat_files:
        bp = os.path.join(bundled_data, name)
        lp = os.path.join(DATA_DIR, name)
        if not os.path.isfile(bp):
            continue
        try:
            with open(bp, "r", encoding="utf-8") as f:
                bundled = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(bundled, dict):
            continue
        if not os.path.isfile(lp):
            local = {}
        else:
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    local = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(local, dict):
                continue
        added = False
        for key, val in bundled.items():
            if key not in local:
                local[key] = val
                added = True
        if added:
            try:
                with open(lp, "w", encoding="utf-8") as f:
                    json.dump(local, f, indent=2)
            except OSError:
                pass

    # base_settings.json: merge under "sets", leave "default" alone unless
    # the local file is missing one entirely.
    bp = os.path.join(bundled_data, "base_settings.json")
    lp = os.path.join(DATA_DIR, "base_settings.json")
    if os.path.isfile(bp):
        try:
            with open(bp, "r", encoding="utf-8") as f:
                bundled = json.load(f)
        except (OSError, ValueError):
            bundled = None
        if isinstance(bundled, dict):
            if not os.path.isfile(lp):
                local = {}
            else:
                try:
                    with open(lp, "r", encoding="utf-8") as f:
                        local = json.load(f)
                except (OSError, ValueError):
                    local = None
            if isinstance(local, dict):
                bundled_sets = bundled.get("sets") or {}
                local_sets = local.get("sets")
                if not isinstance(local_sets, dict):
                    local_sets = {}
                    local["sets"] = local_sets
                added = False
                for key, val in bundled_sets.items():
                    if key not in local_sets:
                        local_sets[key] = val
                        added = True
                if "default" not in local and "default" in bundled:
                    local["default"] = bundled["default"]
                    added = True
                if added:
                    try:
                        with open(lp, "w", encoding="utf-8") as f:
                            json.dump(local, f, indent=2)
                    except OSError:
                        pass


def load_json(name, default=None):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
