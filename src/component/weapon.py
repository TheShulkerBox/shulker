from typing import Any, Iterable

from component.type import Component
from lib.errors import CustomComponentError


class Weapon(Component):
    damage: float | None = None
    speed: float | None = None
    weight: str | None = None

    def make_modifiers(self, type: str, value: float) -> Iterable[dict[str, Any]]:
        yield {
            "type": type,
            "slot": "mainhand",
            "id": "weapon.mainhand",
            "amount": value,
            "operation": "add_value",
        }

    def build(self) -> dict[str, Any]:
        modifiers = []

        if self.damage is not None:
            modifiers.extend(self.make_modifiers("attack_damage", self.damage))

        if self.speed is not None:
            self.speed = (4-self.speed)
            modifiers.extend(self.make_modifiers("attack_speed", -self.speed))

        if self.weight is not None:
            if self.weight is "light":
                ...
            if self.weight is "medium":
                ...
            if self.weight is "heavy":
                ...

        if modifiers:
            return {"attribute_modifiers": modifiers}

        raise CustomComponentError(
            "Need to define one of ['damage', 'speed', 'weight']",
            "weapon",
            self,
        )
