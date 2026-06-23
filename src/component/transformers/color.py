from typing import Any

from component.type import Transformer
from lib.errors import CustomComponentError


def parse_hex_color(color: str, component: Transformer) -> int:
    color = color.removeprefix("#")

    if len(color) == 8:
        color = color[:6]  # handles VSCode auto-picker adding transparency
    elif len(color) != 6:
        raise CustomComponentError(
            f"Color needs to be in form '#aabbcc' (received: '{color}')",
            component.name(),
            component,
        )

    return int(color, 16)


class DyedColor(Transformer, base_type=str | Any):
    """Allows you to write dyed colors using traditional hex formatting."""

    def build(self) -> int | None:
        if type(color := self.base_type) is str:
            return parse_hex_color(color, self)


class PotionContents(Transformer, base_type=dict[str, Any] | Any):
    """Allows potion custom colors to use traditional hex formatting."""

    def build(self) -> dict[str, Any] | None:
        if type(color := self.base_type.get("custom_color")) is str:
            return self.base_type | {"custom_color": parse_hex_color(color, self)}
