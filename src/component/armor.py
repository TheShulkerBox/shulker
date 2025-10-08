from typing import Any, Iterable

from component.base import Component
from lib.errors import CustomComponentError
from lib.const import ARMOR_SLOTS


class Armor(Component):
    value: float | None = None
    toughness: float | None = None
    knockback_resistance: float | None = None
    speed: float | None = None

    def make_modifiers(self, type: str, value: float) -> Iterable[dict[str, Any]]:
        for slot in ARMOR_SLOTS:
            yield {
                "type": type,
                "slot": slot,
                "id": "armor." + slot,
                "amount": value,
                "operation": "add_value",
            }

    def render(self) -> dict[str, Any]:
        modifiers = []

        if self.value is not None:
            modifiers.extend(self.make_modifiers("armor", self.value))

        if self.toughness is not None:
            modifiers.extend(self.make_modifiers("armor_toughness", self.toughness))

        if self.knockback_resistance is not None:
            modifiers.extend(
                self.make_modifiers("knockback_resistance", self.knockback_resistance)
            )

        if self.speed is not None:
            modifiers.extend(self.make_modifiers("movement_speed", self.speed))

        if modifiers:
            return {"attribute_modifiers": modifiers}

        raise CustomComponentError(
            "Need to define one of ['value', 'toughness', 'knockback_resistance', 'speed']",
            "armor",
            self,
        )
