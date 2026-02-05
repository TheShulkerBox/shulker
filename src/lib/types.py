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
