from enum import Enum, auto


class DuelsMapStatus(str, Enum):
    """Status of a duel map."""

    INACTIVE = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
