"""Application tabs."""

from netforge.ftd.dialog import FtdTab
from netforge.tabs.base import BaseTab
from netforge.tabs.generate import GenerateTab
from netforge.tabs.guide import GuideTab
from netforge.tabs.models import ModelsTab
from netforge.tabs.profiles import ProfilesTab
from netforge.tabs.roles import RolesTab

__all__ = [
    "BaseTab",
    "FtdTab",
    "GenerateTab",
    "GuideTab",
    "ModelsTab",
    "ProfilesTab",
    "RolesTab",
]
