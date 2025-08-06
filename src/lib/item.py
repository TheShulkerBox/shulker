import copy
from inspect import signature, Signature
from typing import Any, ClassVar
from src.lib.helpers import title_case_to_snake_case, nbt_dump, deep_merge_dicts
from src.lib.text import theme


class ItemError(Exception):
    """Exceptions related to custom items"""


class ComponentError(ItemError):
    """An Item Error specific towards custom components and transformers"""

    def __init__(self, name: str, component: Any, signature: Signature):
        super().__init__(
            f"Component `{name}` is invalid: `{type(component)}` (`{component}`).\n"
            "Expected `dict` with schema: \n"
            + "\n".join(
                f"  {name}: {param.annotation}"
                for name, param in signature.parameters.items()
                if name != "self"
            )
        )


class ItemMeta(type):
    """Metaclass for item classes.
    
    This essentially works as a custom type for all items. Since we do not instantiate items,
    we use metaclasses to effectively turn class definitions into objects. This allows us
    to define items and their components in a more Pythonic way, while still allowing us
    to dynamically define behavior.

    The metaclass only activates on usage of the `.components` property. This triggers
    a search of all of the members on the class, deciphering whether the member is a 
    component or some custom logic, applying all of our changes, and then returning
    a vanilla set of components with various amounts of metadata.
    
    The custom logic defined are class methods with a name that begins with either
    - "{name}_component"
    - "{name}_transformer"

    These act as modifiers that either return a new set of components or a modified value
    for a component that lets us define a lot of custom features (see `item` for full usage).
    """

    registered_items: ClassVar[dict[str, "ItemMeta"]] = {}
    _namespace: dict[str, Any]

    def __new__(cls, name: str, bases: list[type], namespace: dict[str, Any]):
        if name == "item":
            return super().__new__(cls, name, bases, namespace)

        if name.lower() != name:
            raise ItemError(
                f"item '{name}' should be defined with `snake_case` "
                f"('{title_case_to_snake_case(name)}')."
            )

        cls.registered_items[name] = new_cls = super().__new__(
            cls, name, bases, namespace
        )
        return new_cls

    @property
    def components(self):
        output_components = {}
        callable_members = {}
        custom_components = []  # to remove later

        # Split namespace into callable and non-callable members
        for member in dir(self):
            if not member.startswith("_") and (val := getattr(self, member)) is not None:
                if callable(val):
                    callable_members[member] = val
                else:
                    output_components[member] = copy.deepcopy(val)

        # inject custom data
        output_components = deep_merge_dicts(output_components, {"custom_data": {"item_id": self.name}})

        # For each callable member, handle component and transformer
        for k, func in callable_members.items():

            # Custom components return a dictionary containing one or more components
            if (index := k.find("_component")) > 1:
                name = k[:index]
                sig = signature(func)

                # If the component is defined in the item, apply the function
                if component := output_components.get(name):
                    try:
                        # Call the custom component function based on the signature 
                        if type(component) is not dict:
                            if len(sig.parameters) > 1:
                                raise ComponentError(name, component, sig)
                            new_namespace = func(component)
                        else:
                            new_namespace = func(**component)

                        # If our result exists, deeply merge our new components
                        # We also inject some metadata
                        if new_namespace is not None:
                            metadata = {"custom_components": {name: component}}
                            output_components["custom_data"] = deep_merge_dicts(output_components["custom_data"], metadata)
                            output_components = deep_merge_dicts(output_components, new_namespace)
                            custom_components.append(name)

                    except Exception as e:
                        raise ComponentError(name, component, sig) from e

            # Transformers modify the value of an existing component
            elif (index := k.find("_transformer")) > 1:
                name = k[:index]
                
                # If the component exists, apply the transformer function
                if name in output_components:
                    if (value := func(output_components[name])) is not None:
                        output_components[name] = value

        del output_components["id"]
        for component in custom_components:
            if component in output_components:
                del output_components[component]
        return output_components
    
    @property
    def name(self):
        return self.__name__

    @property
    def has_id(self):
        return "id" in self.__dict__

    def item_string(self):
        if not self.has_id:
            raise ItemError(f"`{self.name}` item must define an `id`!")

        components = ",".join(f"{k}={nbt_dump(v)}" for k, v in self.components.items())
        return f"{self.id}[{components}]"

    def conditional_string(self):
        id = self.__dict__.get("id", "*")
        return f"{id}[custom_data~{{item_id:'{self.name}'}}]"

    __neg__ = __invert__ = conditional_string
    __pos__ = __str__ = item_string

    def __call__(*_, **__):
        raise ItemError("`item` classes cannot be instantiated, see docstring.")


class base_item(metaclass=ItemMeta):
    """item is the base class for all items in the data pack. This is a special behaving structure that
    barely resembles a class leveraging metaclasses.

    The basic structure is to define all components as "class variables" and then use custom methods
    to define special behavior to simplify component construction. This allows you to abstract
    complex behavior as isolated "custom components" or "component transformers" that can be reused
    across multiple items.
    
    ```
    class basic_item(item):
        id = "minecraft:stone"
        item_name = {text: "Basic Item", color: theme.primary}
        lore = ["This is a basic item.", "It does nothing special."]
    ```
    This item just uses vanilla components to define a stone item with a custom name and lore.

    ```
    class custom_item(item):
        id = "minecraft:custom_item"
        item_name = {text: "Custom Item", color: theme.primary}
        lore = ["This is a custom item.", "It has special behavior."]
        test_component = false
        
        def test_component(val: bool):
            return {"enchantment_glint_override": val}
    ```
    Here, we define a basic `test_component` that converts a `bool` into a new set of vanilla components.

    ```
    class custom_item_2(item):
        id = "minecraft:custom_item_2"
        item_name = {text: "Custom Item 2", color: theme.primary}
        lore = ["This is another custom item.", "It has special behavior."]
        dyed_color = "#ff0000"
    ```
    This item uses a `dyed_color` transformer that is automatically transformed into a color integer. Note, the
    implementation for this transformer is defined in the `item` class itself, so you can use it in any item.
    
    Custom components are functions that **must** end with "_component" and define a new component that gets converted
    into one or more components. This is useful for defining a simple interface for coordinating multiple components.
    Custom components can even define their own functions and other resource files in order to achieve it's purpose.

    Component transformers on the other hand are functions that **must** end with "_transformer" and are used to transform
    an existing component's value into a new value. If the transformer returns `None`, no action is taken. This is useful
    when providing multiple input types for a component, such as a color that can be either a string or an integer.
    """
    
    tool = {"can_destroy_blocks_in_creative": False, "rules": []}

    def dyed_color_transformer(color: str | Any):
        """Allows you to write dyed colors using traditional hex formatting"""

        if type(color) is str:
            return int(color.removeprefix("#"), 16)

    def lore_transformer(lore: str | list[str] | list[dict[str, Any]]):
        """Allows you to write lore using regular strings and auto applies formatting"""

        if type(lore) is str:
            lore = [lore]
        
        transformed = []
        for line in lore:
            if type(line) is str:
                # we auto apply server theming if non-specified
                transformed.append({"text": line, "color": theme.secondary, "italic": False})
            else:
                transformed.append(line)
        
        return transformed

class armor_item(base_item):
    """Makes armor unequipable while providing helper attribute components"""

    tooltip_display = {"hidden_components": ["minecraft:enchantments"]}
    enchantments = {"binding_curse": 1}
    enchantment_glint_override = False

    def armor_component(
        slot: str,
        value: float | None = None,
        toughness: float | None = None,
        knockback_resistance: float | None = None,
        speed: float | None = None
    ):
        modifiers = []

        if value is not None:
            modifiers.append({
                "type": "armor",
                "slot": slot,
                "id": "armor." + slot,
                "amount": value,
                "operation": "add_value",
            })

        if toughness is not None:
            modifiers.append({
                "type": "armor_toughness",
                "slot": slot,
                "id": "armor." + slot,
                "amount": toughness,
                "operation": "add_value",
            })

        if knockback_resistance is not None:
            modifiers.append({
                "type": "knockback_resistance",
                "slot": slot,
                "id": "armor." + slot,
                "amount": knockback_resistance,
                "operation": "add_value",
            })

        if speed is not None:
            modifiers.append({
                "type": "movement_speed",
                "slot": slot,
                "id": "armor." + slot,
                "amount": speed,
                "operation": "add_value",
            })

        if modifiers:
            return {"attribute_modifiers": modifiers}


class weapon_item(base_item):
    """Provides weapon customization components"""

    def weapon_component(
        damage: float | None = None,
        speed: float | None = None,
        knockback: float | None = None,
        # crit: float | None,
        **kwargs,  # there are actual weapon stuff we need to pass through
    ):
        modifiers = []

        if damage is not None:
            modifiers.append({
                "type": "attack_damage",
                "slot": "mainhand",
                "id": "weapon",
                "amount": damage,
                "operation": "add_value",
            })

        if speed is not None:
            modifiers.append({
                "type": "attack_speed",
                "slot": "mainhand",
                "id": "weapon",
                "amount": speed,
                "operation": "add_value",
            })
            modifiers.append({
                "type": "attack_speed",
                "slot": "offhand",
                "id": "weapon",
                "amount": speed,
                "operation": "add_value",
            })

        if knockback is not None:
            modifiers.append({
                "type": "attack_knockback",
                "slot": "mainhand",
                "id": "weapon",
                "amount": knockback,
                "operation": "add_value",
            })
            modifiers.append({
                "type": "attack_knockback",
                "slot": "offhand",
                "id": "weapon",
                "amount": knockback,
                "operation": "add_value",
            })

        output = {}
        if modifiers:
            output |= {"attribute_modifiers": modifiers}
        
        if kwargs:
            output |= kwargs
        
        if output:
            return output
