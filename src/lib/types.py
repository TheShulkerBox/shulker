from typing import Annotated, Any
from bolt_expressions import ScoreSource, DataSource

IntLike: Annotated[type, "Works like an int for runtime math"] = (
    int | ScoreSource | DataSource
)
FloatLike: Annotated[type, "Works like an float/double for runtime math"] = (
    float | ScoreSource | DataSource
)
StringLike: Annotated[type, "Works like an str for runtime data"] = str | DataSource
TextComponentLike: Annotated[type, "Works like a text component"] = (
    str | dict[str, "TextComponentLike"] | list["TextComponentLike"] | DataSource
)
CompoundLike: Annotated[type, "Works like a nbt compound"] = dict[str, Any] | DataSource

# Path Types
FunctionPath: Annotated[type, "Path to a function"] = str
AdvancementPath: Annotated[type, "Path to an advancement"] = str
PredicatePath: Annotated[type, "Path to a predicate"] = str


class Remove:
    """Sentinel class for removal operations. do not instantiate."""
    def __init__(self):
        raise NotImplementedError("Do not instantiate `Remove`")
