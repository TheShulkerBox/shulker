from typing import Any, Literal, TypeAlias
from bolt_expressions import ScoreSource, DataSource

IntLike: TypeAlias = int | ScoreSource | DataSource
"""Works like an int for runtime math"""

FloatLike: TypeAlias = float | ScoreSource | DataSource
"""Works like a float/double for runtime math"""

NumberLike: TypeAlias = IntLike | FloatLike
"""Works as an IntLike or a FloatLike"""

StringLike: TypeAlias = str | DataSource
"""Works like a str for runtime data"""

TextComponentLike: TypeAlias = (
    str | dict[str, "TextComponentLike"] | list["TextComponentLike"] | DataSource
)
"""Works like a text component"""

CompoundLike: TypeAlias = dict[str, Any] | DataSource
"""Works like an nbt compound"""

# Path Types
FunctionPath: TypeAlias = str
"""Path to a function"""

AdvancementPath: TypeAlias = str
"""Path to an advancement"""

PredicatePath: TypeAlias = str
"""Path to a predicate"""

SlotLiteral: TypeAlias = Literal[
    "mainhand", "offhand", "head", "chest", "legs", "feet", "any"
]
"""A slot in the player's inventory"""

class Remove:
    """Sentinel class for removal operations. do not instantiate."""
    def __init__(self):
        raise NotImplementedError("Do not instantiate `Remove`")
