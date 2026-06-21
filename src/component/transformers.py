from typing import Any

from minecraft_text_components import TextComponent

from component.type import Transformer
from lib.text import Theme
from lib.errors import CustomComponentError


class DyedColor(Transformer, base_type=str | Any):
    """Allows you to write dyed colors using traditional hex formatting"""

    def build(self) -> int | None:
        if type(color := self.base_type) is str:
            color = color.removeprefix("#")

            if len(color) == 8:
                color = color[:6]  # handles VSCode auto-picker adding transparency
            elif len(color) != 6:
                raise CustomComponentError(
                    "Color needs to be in form '#aabbcc' (received: '{color}')",
                    "dyed_color",
                    self,
                )

            return int(color, 16)


class PotionContents(Transformer, base_type=dict[str, Any] | Any):
    """Allows you to write dyed colors using traditional hex formatting"""

    def build(self) -> int | None:
        if type(color := self.base_type.get("custom_color")) is str:
            color = color.removeprefix("#")

            if len(color) == 8:
                color = color[:6]  # handles VSCode auto-picker adding transparency
            elif len(color) != 6:
                raise CustomComponentError(
                    "Color needs to be in form '#aabbcc' (received: '{color}')",
                    "dyed_color",
                    self,
                )

            return self.base_type | {"custom_color": int(color, 16)}
        return self.base_type


class Lore(Transformer, base_type=str | list[str] | list[dict[str, Any]] | Any):
    """Allows you to write lore using regular strings and auto applies formatting"""

    def build(self) -> list[TextComponent]:
        if type(lore := self.base_type) is str:
            lore = [lore]

        return [
            (
                {"text": line, "color": Theme.Secondary, "italic": False}
                if type(line) is str
                else line
            )
            for line in lore
        ]
