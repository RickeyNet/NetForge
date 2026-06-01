"""Config renderer: dict inputs to IOS configuration strings."""

from netforge.render.l3 import _ospf_config_for_edit, _vlan_id_remap
from netforge.render.normalize import (
    _L3_LOOPBACK_COMMANDS_DEFAULT,
    _L3_LOOPBACK_DEFAULTS,
    _L3_MGMT_SVI_DEFAULTS,
    _L3_ROUTED_MGMT_DEFAULTS,
    _normalize_l3_sections,
)
from netforge.render.render import render_config, render_config_sections
from netforge.render.sections import _ntp_commands_for_edit

__all__ = [
    "render_config",
    "render_config_sections",
    "_normalize_l3_sections",
    "_ntp_commands_for_edit",
    "_ospf_config_for_edit",
    "_vlan_id_remap",
    "_L3_LOOPBACK_DEFAULTS",
    "_L3_LOOPBACK_COMMANDS_DEFAULT",
    "_L3_ROUTED_MGMT_DEFAULTS",
    "_L3_MGMT_SVI_DEFAULTS",
]
