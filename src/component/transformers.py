from typing import Any

from minecraft_text_components import TextComponent

from component.base import Transformer
from lib.text import theme
from lib.errors import CustomComponentError


class DyedColor(Transformer):
    """Allows you to write dyed colors using traditional hex formatting"""

    color: str | Any

    def render(self) -> int | None:
        if type(color := self.color) is str:
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


class Lore(Transformer):
    lore: str | list[str] | list[dict[str, Any]]

    def render(self) -> list[TextComponent]:
        """Allows you to write lore using regular strings and auto applies formatting"""

        if type(lore := self.lore) is str:
            lore = [lore]

        return [
            (
                {"text": line, "color": theme.secondary, "italic": False}
                if type(line) is str
                else line
            )
            for line in lore
        ]
