"""
TEMP until bolt supports enums
"""

from enum import Enum


class Tag(str, Enum):
    """Organizational tags for maps. Used for map queuing and map pools."""

    Competitive = "competitive"
    All = "all"
    CTF = "ctf"
    FTM = "ftm"
    Deathmatch = "deathmatch"
    Active = "active"
