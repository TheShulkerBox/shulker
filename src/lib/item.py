import copy
from inspect import signature, Signature
import json
from typing import Any, ClassVar


def title_case_to_snake_case(title_case_str):
    snake_case_str = []
    for index, char in enumerate(title_case_str):
        # TitleCase usually starts with an uppercase so we ignore the first character
        if char.isupper() and index != 0:
            snake_case_str.append("_")

        snake_case_str.append(char.lower())

    return "".join(snake_case_str)


def nbt_dump(obj: dict[str, Any]):
    def serialize(obj: Any):
        match obj:
            case dict():
                items = []
                for key, value in obj.items():
                    serialized_key = key
                    serialized_value = serialize(value)
                    items.append(f"{serialized_key}: {serialized_value}")
                return "{" + ", ".join(items) + "}"
            case list():
                items = [serialize(element) for element in obj]
                return "[" + ", ".join(items) + "]"
            case str():
                return f"'{obj}'"
            case _:
                return json.dumps(obj)

    return serialize(obj)


class ItemError(Exception): ...


class ComponentError(ItemError):
    def __init__(self, name: str, component: Any, signature: Signature):
        super().__init__(
            f"Component `{name}` is invalid: `{type(component)}` (`{component}`).\n"
            "Expected `dict` with schema: \n"
            + "\n".join(
                f"  {name}: {param.annotation.__name__}"
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
                            metadata = {
                                "custom_components": {name: component},
                                "_custom_components": [name]
                            }
                            output_components["custom_data"] = deep_merge_dicts(output_components["custom_data"], metadata)
                            
                            output_components = deep_merge_dicts(output_components, new_namespace)

                    except Exception as e:
                        raise ComponentError(name, component, sig) from e

            # Transformers modify the value of an existing component
            elif (index := k.find("_transformer")) > 1:
                name = k[:index]
                
                # If the component exists, apply the transformer function
                if name in output_components:
                    if (value := func(output_components[name])) is not None:
                        output_components[name] = value

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
        return f"{id}[custom_data~{{item_ids:['{self.name}']}}]"

    __neg__ = __invert__ = conditional_string
    __pos__ = __str__ = item_string

    def __call__(*_, **__):
        raise ItemError("`item` classes cannot be instantiated, see docstring.")


def deep_merge_dicts(d1: dict[str, Any], d2: dict[str, Any]) -> dict[str, Any] | None:
    """Deep merge two dictionaries, including lists, using match statement.

    Args:
        d1 (dict): The first dictionary.
        d2 (dict): The second dictionary to be merged into the first.

    Returns:
        dict: The deeply merged dictionary.
    """

    merged = copy.deepcopy(dict(d1))  # Make a copy of the first dictionary

    for key, value in d2.items():
        if key in merged:
            match (merged[key], value):
                case (dict() as d1_value, dict() as d2_value):
                    merged[key] = deep_merge_dicts(d1_value, d2_value)
                case (list() as list1, list() as list2):
                    merged[key] = list1 + list2
                case _:
                    merged[key] = value
        else:
            merged[key] = value

    return merged
