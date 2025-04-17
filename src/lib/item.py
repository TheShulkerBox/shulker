import copy
from inspect import signature, Signature
import json
from typing import Any, ClassVar
from abc import ABC

def title_case_to_snake_case(title_case_str):
    snake_case_str = []
    for index, char in enumerate(title_case_str):
        # TitleCase usually starts with an uppercase so we ignore the first character
        if char.isupper() and index != 0:
            snake_case_str.append('_')
        
        snake_case_str.append(char.lower())

    return ''.join(snake_case_str)


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
    registered_items: ClassVar[dict[str, "ItemMeta"]] = {}
    _components: dict[str, Any]

    def __new__(cls, name: str, bases: list[type], namespace: dict[str, Any]):
        if name == "item":
            return super().__new__(cls, name, bases, namespace)

        if name.lower() != name:
            raise ItemError(
                f"item '{name}' should be defined with `snake_case` "
                f"('{title_case_to_snake_case(name)}')."
            )
        
        if len(bases) > 1:
            raise ItemError(
                "item classes do not support multiple inheritance\n"
                f"`{name}`: `{bases}`"
            )

        prev_dict = {k: v for k, v in bases[0].__dict__.items() if not k.startswith("__")}
        namespace = cls.prep_namespace(name, deep_merge_dicts(prev_dict, namespace))

        cls.registered_items[name] = new_cls = super().__new__(cls, name, bases, namespace)
        return new_cls
    
    @classmethod
    def prep_namespace(cls, name: str, namespace: dict[str, Any]):
        namespace.setdefault("custom_data", {})
        namespace["custom_data"].setdefault("item_ids", [])
        namespace.setdefault("_custom_components", [])
        namespace["custom_data"].setdefault("custom_components", {})
        namespace["custom_data"]["item_id"] = name
        namespace["custom_data"]["item_ids"].append(name)
        
        namespace = cls.resolve_callables(namespace)
        namespace["_components"] = cls.calculate_components(namespace)
        return namespace
    
    @property
    def components(self):
        return self._components
    
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
    __pos__ = __str__  = item_string

    @classmethod
    def calculate_components(cls, namespace: dict[str, Any]):
        return {
            k: v
            for k, v in namespace.items()
            if (
                not k.startswith("_") 
                and not callable(v)
                and k not in ["id", "minecraft:id"]
                and k not in namespace.get("_custom_components", [])
                and v is not drop
            )
        }
    
    @classmethod
    def resolve_callables(cls, namespace: dict[str, Any]):
        for k, func in namespace.items():
            if not callable(func):
                continue
            
            if (index := k.find("_component")) > 1:
                name = k[:index]
                sig = signature(func)
                
                if component := namespace.get(name):
                    if type(component) is not dict:
                        if len(sig.parameters) > 1:
                            raise ComponentError(name, component, sig)
                        
                        new_namespace = func(component)
                    
                    else:
                        new_namespace = func(**component)
                    
                    if new_namespace is not None:
                        namespace["custom_data"]["custom_components"] = deep_merge_dicts(
                            namespace["custom_data"]["custom_components"],
                            {name: component}
                        )
                        namespace = deep_merge_dicts(namespace, new_namespace)
                        namespace["_custom_components"].append(name)

            elif (index := k.find("_transformer")) > 1:
                name = k[:index]

                if name in namespace:
                    if (value := func(namespace[name])) is not None:
                        namespace[name] = value

        return namespace
    
                
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


class drop(ABC):
    """Sentinel value to remove components"""
