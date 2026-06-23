from typing import Any

from minecraft_text_components import TextComponent

from component.type import Transformer
from lib.text import Theme


class Lore(Transformer, base_type=str | list[str] | list[dict[str, Any]] | Any):
    """Allows you to write lore using regular strings and auto applies formatting."""

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
