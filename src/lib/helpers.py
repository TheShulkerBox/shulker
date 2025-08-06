from collections.abc import Callable
import copy
import json
from typing import Any


def title_case_to_snake_case(title_case_str: str):
    """Converts a title case string into snake case"""

    snake_case_str = []
    for index, char in enumerate(title_case_str):
        # TitleCase usually starts with an uppercase so we ignore the first character
        if char.isupper() and index != 0:
            snake_case_str.append("_")

        snake_case_str.append(char.lower())

    return "".join(snake_case_str)


def nbt_dump(obj: dict[str, Any]):
    """Helper to dump generic dicts into serialized nbt"""

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
            case bool() as b:
                if b:
                    return "true"
                return "false"
            case _:
                return json.dumps(obj)

    return serialize(obj)


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


class StaticMetaClass(type):
    def __new__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
        namespace = {k: (staticmethod(v) if (not k.startswith("_")) and (isinstance(v, Callable)) else v) for k, v in namespace.items()}
        return super().__new__(
            cls, name, bases, namespace
        )


class Static(metaclass=StaticMetaClass):
    ...
