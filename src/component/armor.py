from typing import Any

from component.meta import component
from lib.errors import CustomComponentError


@component
class armor:
    slot: str
    value: float | None = None
    toughness: float | None = None
    knockback_resistance: float | None = None
    speed: float | None = None

    def make_modifier(self, type: str, value: float) -> dict[str, Any]:
        return {
            "type": type,
            "slot": self.slot,
            "id": "armor." + self.slot,
            "amount": value,
            "operation": "add_value",
        }

    def __call__(self) -> dict[str, Any]:
        modifiers = []

        if self.value is not None:
            modifiers.append(self.make_modifiers("armor", self.value))

        if self.toughness is not None:
            modifiers.append(self.make_modifiers("armor_toughness", self.toughness))

        if self.knockback_resistance is not None:
            modifiers.append(
                self.make_modifiers("knockback_resistance", self.knockback_resistance)
            )

        if self.speed is not None:
            modifiers.append(self.make_modifiers("movement_speed", self.speed))

        if modifiers:
            return {"attribute_modifiers": modifiers}

        raise CustomComponentError(
            "Need to define one of ['value', 'toughness', 'knockback_resistance', 'speed']",
            "armor",
            self,
        )
