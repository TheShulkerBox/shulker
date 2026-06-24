from typing import Any

from component.type import Component
from lib.errors import CustomComponentError


class Armor(Component):
    value: float | None = None
    toughness: float | None = None
    knockback_resistance: float | None = None
    speed: float | None = None

    def default_components(self) -> dict[str, Any]:
        item_id = self.item.id.removeprefix("minecraft:")
        return self.item.ctx.meta["item_component_defaults"].get(item_id, {})

    def component_values(self, name: str) -> list[Any]:
        values = []

        for components in (self.resolved_components, self.default_components()):
            for component_name in (name, f"minecraft:{name}"):
                if value := components.get(component_name):
                    values.append(value)

        return values

    def slot(self) -> str:
        for equippable in self.component_values("equippable"):
            if slot := equippable.get("slot"):
                return slot

        for attribute_modifiers in self.component_values("attribute_modifiers"):
            for modifier in attribute_modifiers:
                if slot := modifier.get("slot"):
                    return slot

        raise CustomComponentError(
            f"Could not infer armor slot for item id {self.item.id!r}. Define an equippable component or use an item with vanilla equippable defaults.",
            "armor",
            self,
        )

    def modifier_id(self, type: str, slot: str) -> str:
        attribute_type = type.removeprefix("minecraft:")
        for attribute_modifiers in self.component_values("attribute_modifiers"):
            for modifier in attribute_modifiers:
                if (
                    modifier.get("slot") == slot
                    and modifier.get("type", "").removeprefix("minecraft:")
                    == attribute_type
                ):
                    return modifier.get("id", "armor." + slot)

        return "armor." + slot

    def make_modifier(self, type: str, value: float) -> dict[str, Any]:
        slot = self.slot()
        return {
            "type": type,
            "slot": slot,
            "id": self.modifier_id(type, slot),
            "amount": value,
            "operation": "add_value",
        }

    def build(self) -> dict[str, Any]:
        modifiers = []

        if self.value is not None:
            modifiers.append(self.make_modifier("armor", self.value))

        if self.toughness is not None:
            modifiers.append(self.make_modifier("armor_toughness", self.toughness))

        if self.knockback_resistance is not None:
            modifiers.append(
                self.make_modifier("knockback_resistance", self.knockback_resistance)
            )

        if self.speed is not None:
            modifiers.append(self.make_modifier("movement_speed", self.speed))

        if modifiers:
            return {"attribute_modifiers": modifiers}

        raise CustomComponentError(
            "Need to define one of ['value', 'toughness', 'knockback_resistance', 'speed']",
            "armor",
            self,
        )
