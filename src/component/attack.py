from typing import Any

from component.type import Component
from lib.errors import CustomComponentError


class Attack(Component):
    damage: float | None = None
    speed: float | None = None
    knockback: float | None = None

    def make_modifier(
        self, type: str, value: float, offhand: bool = True
    ) -> dict[str, Any]:
        return {
            "type": type,
            "slot": "offhand" if offhand else "mainhand",
            "id": "weapon",
            "amount": value,
            "operation": "add_value",
        }

    def build(self) -> dict[str, Any]:
        modifiers = []

        if self.damage is not None:
            modifiers.append(self.make_modifier("attack_damage", self.damage))
            modifiers.append(
                self.make_modifier("attack_damage", self.damage, offhand=False)
            )

        if self.speed is not None:
            modifiers.append(self.make_modifier("attack_speed", self.speed))

        if self.knockback is not None:
            modifiers.append(self.make_modifier("attack_knockback", self.knockback))

        if modifiers:
            return {"attribute_modifiers": modifiers}

        raise CustomComponentError(
            "Need to define one of ['damage', 'speed', 'knockback']",
            "attack",
            self,
        )
