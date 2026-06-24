"""BGP sub-editor for the Site Profiles tab.

Split out of profiles.py to keep that mega-tab manageable. ``BgpEditorMixin``
is mixed into ``ProfilesTab`` and drives the per-instance BGP blocks (local
ASN, peer slots, and the advertising options). It relies on attributes the
tab sets up in its ``_build`` (``bgp_blocks``, ``bgp_container``).
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from netforge.ui.helpers import _attach_context_menu, _autosize_textarea
from netforge.ui.theme import C


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


class BgpEditorMixin:
    """Per-instance BGP blocks: ASN, peer slots, advertising options."""

    if TYPE_CHECKING:
        # Set up by ProfilesTab._build; declared here so type checkers know
        # the mixin relies on them (see module docstring).
        bgp_blocks: list[dict[str, Any]]
        bgp_container: ttk.Frame

    def _update_bgp_collapsed(self):
        """Show only the Add button when no BGP instances; expand once blocks exist."""
        if self.bgp_blocks:
            if not self.bgp_container.winfo_ismapped():
                self.bgp_container.pack(fill="x")
        elif self.bgp_container.winfo_ismapped():
            self.bgp_container.pack_forget()

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
