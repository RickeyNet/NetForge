"""L3 section row editor shared by Generate and Profiles tabs."""

import tkinter as tk
from tkinter import ttk

from netforge.data.iface import _canon_iface
from netforge.render import (
    _L3_LOOPBACK_COMMANDS_DEFAULT,
    _L3_LOOPBACK_DEFAULTS,
    _L3_MGMT_SVI_DEFAULTS,
    _L3_ROUTED_MGMT_DEFAULTS,
)
from netforge.ui.helpers import _attach_context_menu, _autosize_textarea
from netforge.ui.theme import C

_L3_UI_ALIAS = {"loopback": "lb", "routed_mgmt": "rm", "mgmt_svi": "msvi"}

_L3_KINDS = {
    "loopback": {
        "defaults": _L3_LOOPBACK_DEFAULTS,
        "id_field": "number",
        "sw_list": "loopbacks",
        "legacy_sw": {
            "loopback0_ip": "ip", "loopback0_mask": "mask",
            "loopback0_desc": "description",
        },
        "profile": {
            "checkbox": "Loopbacks",
            "add_label": "+ Add Loopback",
            "uniform": "lbcol",
            "columns": (
                ("number", "Number", 1),
                ("ip", "IP (default)", 2),
                ("mask", "Mask (default)", 2),
                ("description", "Description", 3),
            ),
            "new_defaults": {
                "number": "0", "mask": "255.255.255.255",
                "description": "Switch MGMT / Router-ID",
            },
            "textarea": {
                "field": "commands",
                "label": "Interface Config",
                "default": _L3_LOOPBACK_COMMANDS_DEFAULT,
                "hint": (
                    "  IOS lines inside the Loopback interface block.\n"
                    "  Use {{ ip }}, {{ mask }}, and {{ description }} for\n"
                    "  values from the row above / Generate Config Step 3.\n"
                    "  Leave blank to use the default description / ip / no shutdown."
                ),
            },
        },
        "generate": {
            "title": "Loopbacks",
            "hint": "  One row per loopback defined in the profile.",
            "uniform": "genlb",
            "columns": (
                ("number", "Loopback", 1, {"readonly": True, "display": "Loopback{}"}),
                ("ip", "IP", 2),
                ("mask", "Mask", 2),
                ("description", "Description", 3),
            ),
        },
    },
    "routed_mgmt": {
        "defaults": _L3_ROUTED_MGMT_DEFAULTS,
        "id_field": "interface",
        "sw_list": "routed_mgmt_interfaces",
        "legacy_sw": {"routed_mgmt_ip": "ip", "routed_mgmt_mask": "mask"},
        "profile": {
            "checkbox": "Routed Interfaces",
            "add_label": "+ Add Routed Interface",
            "uniform": "rmcol",
            "columns": (
                ("interface", "Interface", 2),
                ("ip", "IP (default)", 2),
                ("mask", "Mask (default)", 2),
                ("description", "Description", 3),
            ),
            "new_defaults": {"description": "Routed Mgmt Uplink"},
        },
        "generate": {
            "title": "Routed Interfaces",
            "hint": "  One row per routed interface defined in the profile.",
            "uniform": "genrm",
            "columns": (
                ("interface", "Interface", 2, {"readonly": True}),
                ("ip", "IP", 2),
                ("mask", "Mask", 2),
            ),
        },
    },
    "mgmt_svi": {
        "defaults": _L3_MGMT_SVI_DEFAULTS,
        "id_field": "vlan",
        "sw_list": "mgmt_svis",
        "legacy_sw": {
            "mgmt_svi_ip": "ip", "mgmt_svi_mask": "mask",
            "mgmt_svi_vlan": "vlan",
        },
        "profile": {
            "checkbox": "Management VLANs",
            "add_label": "+ Add Management VLAN",
            "uniform": "msvicol",
            "columns": (
                ("vlan", "VLAN ID", 1),
                ("ip", "IP (default)", 2),
                ("mask", "Mask (default)", 2),
                ("description", "Description", 3),
            ),
            "new_defaults": {"description": "Switch MGMT"},
        },
        "generate": {
            "title": "Management VLANs",
            "hint": "  One row per management VLAN defined in the profile.",
            "uniform": "genmsvi",
            "columns": (
                ("vlan", "VLAN", 1, {"readonly": True, "display": "Vlan{}"}),
                ("ip", "IP", 2),
                ("mask", "Mask", 2),
                ("description", "Description", 3),
            ),
        },
    },
}


def _l3_entry_key(kind, entry):
    spec = _L3_KINDS[kind]
    val = str(entry.get(spec["id_field"]) or "").strip()
    if kind == "routed_mgmt":
        return _canon_iface(val)
    return val


class L3EntryGrid:
    """Shared row editor for l3_sections profile and generate UIs."""

    def __init__(self, kind, mode):
        self.kind = kind
        self.mode = mode
        self.spec = _L3_KINDS[kind]
        self.rows = []
        self.lf = None
        self.enabled = None
        self.row_frame = None
        self.hint = None

    def build_profile(self, parent):
        cfg = self.spec["profile"]
        self.lf = ttk.LabelFrame(parent, padding=5)
        self.lf.pack(fill="x", padx=5, pady=(4, 0 if self.kind != "mgmt_svi" else 4))
        self.enabled = tk.BooleanVar(value=False)
        top = ttk.Frame(self.lf); top.pack(fill="x")
        ttk.Checkbutton(top, text=cfg["checkbox"],
                        variable=self.enabled).pack(side="left")
        ttk.Button(top, text=cfg["add_label"],
                   command=lambda: self.add()).pack(side="right", padx=(6, 1))
        hdr = ttk.Frame(self.lf); hdr.pack(fill="x", pady=(4, 0))
        for col, (field, label, weight, *_) in enumerate(cfg["columns"]):
            hdr.columnconfigure(col, weight=weight, uniform=cfg["uniform"])
            ttk.Label(hdr, text=label, anchor="w").grid(
                row=0, column=col, sticky="ew", padx=1)
        ttk.Frame(hdr, width=30).grid(row=0, column=len(cfg["columns"]),
                                        padx=(6, 1))
        self.row_frame = ttk.Frame(self.lf); self.row_frame.pack(fill="x")
        ta_cfg = cfg.get("textarea")
        if ta_cfg and ta_cfg.get("hint"):
            ttk.Label(self.lf, style="Hint.TLabel",
                      text=ta_cfg["hint"]).pack(anchor="w", padx=2, pady=(0, 4))
        return self

    def build_generate(self, parent):
        cfg = self.spec["generate"]
        self.lf = ttk.LabelFrame(parent, text=cfg["title"], padding=5)
        self.lf.pack(fill="x", padx=5, pady=4)
        self.hint = ttk.Label(self.lf, style="Hint.TLabel", text=cfg["hint"])
        self.hint.pack(anchor="w", padx=2, pady=(0, 4))
        hdr = ttk.Frame(self.lf); hdr.pack(fill="x")
        for col, col_spec in enumerate(cfg["columns"]):
            field, label, weight = col_spec[:3]
            hdr.columnconfigure(col, weight=weight, uniform=cfg["uniform"])
            ttk.Label(hdr, text=label, anchor="w").grid(
                row=0, column=col, sticky="ew", padx=1)
        self.row_frame = ttk.Frame(self.lf); self.row_frame.pack(fill="x")
        return self

    def clear(self):
        for row in self.rows:
            row["frame"].destroy()
        self.rows.clear()

    def _profile_value_fields(self):
        columns = (self.spec["profile"]["columns"] if self.mode == "profile"
                   else self.spec["generate"]["columns"])
        id_field = self.spec["id_field"]
        return [c[0] for c in columns
                if c[0] not in (id_field, "description")]

    def _entry_has_profile_data(self, entry):
        id_field = self.spec["id_field"]
        if str(entry.get(id_field) or "").strip():
            return True
        if str(entry.get("commands") or "").strip():
            return True
        return any(str(entry.get(f) or "").strip()
                   for f in self._profile_value_fields())

    def _default_row_key(self):
        return f"__default__:{self.kind}"

    def add(self, data=None, editable_key=False):
        if self.mode == "profile":
            columns = self.spec["profile"]["columns"]
            uniform = self.spec["profile"]["uniform"]
            deletable = True
            new_defaults = self.spec["profile"].get("new_defaults", {})
        else:
            columns = self.spec["generate"]["columns"]
            uniform = self.spec["generate"]["uniform"]
            deletable = False
            new_defaults = {}
        data = data or {}
        outer_fr = ttk.Frame(self.row_frame)
        outer_fr.pack(fill="x", pady=1)
        row_fr = ttk.Frame(outer_fr)
        row_fr.pack(fill="x")
        fields = {}
        for col, col_spec in enumerate(columns):
            field = col_spec[0]
            weight = col_spec[2]
            opts = col_spec[3] if len(col_spec) > 3 else {}
            row_fr.columnconfigure(col, weight=weight, uniform=uniform)
            readonly = opts.get("readonly") and not (
                editable_key and field == self.spec["id_field"])
            if readonly:
                raw = str(data.get(field, "") or "").strip()
                if field == "number" and not raw:
                    raw = "0"
                text = opts.get("display", "{}").format(raw)
                widget = text
                ttk.Label(row_fr, text=text, anchor="w").grid(
                    row=0, column=col, sticky="ew", padx=1)
            else:
                widget = ttk.Entry(row_fr)
                widget.grid(row=0, column=col, sticky="ew", padx=1)
                _attach_context_menu(widget)
                val = data.get(field, "")
                if not val and field in new_defaults:
                    val = new_defaults[field]
                if val:
                    widget.insert(0, str(val))
            fields[field] = widget
        if deletable:
            ttk.Button(row_fr, text="X", width=3, style="Del.TButton",
                       command=lambda fr=outer_fr: self._delete(fr)
                       ).grid(row=0, column=len(columns), padx=(6, 1))
        commands_widget = None
        if self.mode == "profile":
            ta_cfg = self.spec["profile"].get("textarea")
            if ta_cfg:
                ta_fr = ttk.Frame(outer_fr)
                ta_fr.pack(fill="x", pady=(4, 0))
                ttk.Label(ta_fr, text=ta_cfg.get("label", "Commands"),
                          anchor="w").pack(anchor="w", padx=1)
                commands_widget = tk.Text(
                    ta_fr, height=3, font=("Consolas", 9),
                    bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
                    selectbackground=C["sel_bg"], relief="flat", bd=2,
                    wrap="none")
                commands_widget.pack(fill="x", padx=1, pady=(2, 0))
                _attach_context_menu(commands_widget)
                _autosize_textarea(commands_widget, min_h=2, max_h=12)
                ta_field = ta_cfg["field"]
                ta_val = (data.get(ta_field) or "").strip()
                if not ta_val and not data:
                    ta_val = ta_cfg.get("default", "")
                if ta_val:
                    commands_widget.insert("1.0", ta_val)
        self.rows.append({"frame": outer_fr, "fields": fields,
                          "commands": commands_widget})

    def _delete(self, frame):
        self.rows = [r for r in self.rows if r["frame"] is not frame]
        frame.destroy()

    def populate(self, entries, editable_key=False):
        saved = {}
        for row in self.rows:
            key = self._row_key(row, editable_key)
            if key:
                saved[key] = {f: self._field_get(row, f)
                              for f, _ in self._iter_fields(row)}
                ta = row.get("commands")
                if ta is not None:
                    saved[key]["commands"] = ta.get("1.0", "end").strip()
        self.clear()
        for entry in entries or []:
            entry = dict(entry)
            if self.kind == "loopback" and not str(entry.get("number") or "").strip():
                entry["number"] = "0"
            key = _l3_entry_key(self.kind, entry)
            if self.kind != "loopback" and not key:
                if not self._entry_has_profile_data(entry):
                    continue
            self.add(entry, editable_key=editable_key)
            vals = saved.get(key, {})
            cur = self.rows[-1]
            for field, val in vals.items():
                if field == "commands":
                    ta = cur.get("commands")
                    if ta is not None:
                        ta.delete("1.0", "end")
                        if val:
                            ta.insert("1.0", val)
                    continue
                w = cur["fields"].get(field)
                if hasattr(w, "insert"):
                    w.delete(0, "end")
                    if val:
                        w.insert(0, val)

    def _row_key(self, row, editable_key):
        id_field = self.spec["id_field"]
        w = row["fields"].get(id_field)
        if hasattr(w, "get"):
            val = w.get().strip()
        elif isinstance(w, str):
            if self.kind == "loopback":
                val = w.replace("Loopback", "").strip()
            elif self.kind == "mgmt_svi":
                val = w.replace("Vlan", "").strip()
            else:
                val = w.strip()
        else:
            val = str(w or "").strip()
        if self.kind == "routed_mgmt":
            return _canon_iface(val) if val else self._default_row_key()
        return val if val else self._default_row_key()

    def _iter_fields(self, row):
        for field, w in row["fields"].items():
            if hasattr(w, "get"):
                yield field, w

    def _field_get(self, row, field):
        w = row["fields"].get(field)
        return w.get().strip() if hasattr(w, "get") else ""

    def collect_profile_entries(self):
        id_field = self.spec["id_field"]
        defaults = self.spec["defaults"]
        out = []
        for row in self.rows:
            entry = {}
            for field, w in self._iter_fields(row):
                val = w.get().strip()
                if field == "number" and not val:
                    val = "0"
                entry[field] = val
            if not entry.get(id_field) and not self._entry_has_profile_data(entry):
                continue
            if not entry.get("description"):
                entry["description"] = defaults.get("description", "")
            if not entry.get("mask") and defaults.get("mask"):
                entry["mask"] = defaults["mask"]
            ta_cfg = (self.spec["profile"].get("textarea")
                      if self.mode == "profile" else None)
            if ta_cfg:
                ta = row.get("commands")
                if ta is not None:
                    entry[ta_cfg["field"]] = ta.get("1.0", "end").strip()
            out.append(entry)
        return out

    def _row_has_sw_data(self, item):
        return any(str(item.get(f) or "").strip()
                   for f in self._profile_value_fields())

    def collect_sw_items(self, editable_key=False):
        items = []
        id_field = self.spec["id_field"]
        for row in self.rows:
            item = {}
            for field, w in self._iter_fields(row):
                item[field] = w.get().strip()
            w = row["fields"].get(id_field)
            if editable_key and hasattr(w, "get"):
                key_val = w.get().strip()
            elif isinstance(w, str):
                if self.kind == "loopback":
                    key_val = w.replace("Loopback", "").strip()
                elif self.kind == "mgmt_svi":
                    key_val = w.replace("Vlan", "").strip()
                else:
                    key_val = w.strip()
            else:
                key_val = str(w or "").strip()
            if not key_val:
                # Site profiles often leave routed_mgmt.interface blank
                # so one Step 3 IP applies to whichever uplink port was
                # assigned in Step 2. Keep those rows (keyed by "").
                if (self.mode == "generate" and self.kind == "routed_mgmt"
                        and self._row_has_sw_data(item)):
                    key_val = ""
                else:
                    continue
            item[id_field] = key_val
            if self.kind == "loopback":
                desc_w = row["fields"].get("description")
                if hasattr(desc_w, "get"):
                    item["description"] = desc_w.get().strip()
                item.setdefault("mask", "255.255.255.255")
                item.setdefault("description", "")
            items.append(item)
        return items


def _collect_l3_sw_from_grids(grids, editable_vlan=False):
    sw = {}
    for kind, grid in grids.items():
        spec = _L3_KINDS[kind]
        editable = editable_vlan and kind == "mgmt_svi"
        items = grid.collect_sw_items(editable_key=editable)
        sw[spec["sw_list"]] = items
        _apply_l3_legacy_sw_aliases(sw, kind, items)
    return sw


def _site_routed_mgmt_override(sw):
    """Per-switch routed uplink values when the profile interface is blank."""
    items = [i for i in (sw.get("routed_mgmt_interfaces") or [])
             if isinstance(i, dict)]
    blanks = [i for i in items if not str(i.get("interface") or "").strip()]
    if len(blanks) == 1:
        return blanks[0]
    legacy_ip = (sw.get("routed_mgmt_ip") or "").strip()
    legacy_mask = (sw.get("routed_mgmt_mask") or "").strip()
    if legacy_ip or legacy_mask:
        return {"interface": "", "ip": legacy_ip, "mask": legacy_mask}
    return {}


def _apply_l3_legacy_sw_aliases(sw, kind, items):
    spec = _L3_KINDS[kind]
    legacy = spec.get("legacy_sw") or {}
    if not items:
        for legacy_key in legacy:
            sw[legacy_key] = ""
        return
    first = items[0]
    for legacy_key, field in legacy.items():
        sw[legacy_key] = first.get(field, "")


