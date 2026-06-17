from collections.abc import Callable, Iterator
import copy
from contextlib import contextmanager
import dataclasses
import json
import re
from typing import Any, Literal, Protocol, Union, get_args, get_origin, overload
import zlib

import dacite
from typeguard import check_type as _check_type, TypeCheckError


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
                if "'" not in obj:
                    return f"'{obj}'"
                return f'"{obj}"'
            case bool() as b:
                if b:
                    return "true"
                return "false"
            case _:
                return json.dumps(obj)

    return serialize(obj)


@overload
def deep_merge_dicts(
    d1: dict[str, Any], d2: dict[str, Any], inplace: Literal[False]
) -> dict[str, Any]: ...


@overload
def deep_merge_dicts(
    d1: dict[str, Any], d2: dict[str, Any], inplace: Literal[True]
) -> None: ...


def deep_merge_dicts(
    d1: dict[str, Any], d2: dict[str, Any], inplace: bool = False
) -> dict[str, Any] | None:
    """Deep merge two dictionaries, including lists, using match statement.

    Args:
        d1 (dict): The first dictionary.
        d2 (dict): The second dictionary to be merged into the first.

    Returns:
        dict: The deeply merged dictionary.
    """
    if inplace:
        merged = d1
    else:
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


class Singleton(type):
    def __new__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
        return super().__new__(cls, name, bases, namespace)()


class BranchProtocol(Protocol):
    def __branch__(self) -> Iterator[Literal[True]]: ...


def branch(func: Callable[..., Iterator[Literal[True]]]) -> BranchProtocol:
    """Decorator to convert a method into a class with a `__branch__` method. This is used to
    allow methods to be used in `if` statements in Bolt scripts.

    ```python
    from src.lib.helpers import branch

    class MyClass:
        @branch
        def my_method(self) -> Iterator[Literal[True]]:
            yield True
    ```
    """

    class BranchWrapper:
        __branch__ = contextmanager(func)

    return BranchWrapper()


def id_to_number(id: str) -> int:
    """Converts a string id to a numerical one using a hash function.

    Since hash functions return 64-bit integers, we mask it to 31 bits to ensure it's positive
    and fits within the range of a standard scoreboard.
    """
    return zlib.crc32(id.encode()) & int("0x7FFFFFFF", 16)


def coerce_type(value: Any, t: type) -> Any:
    """Coerces a value to a type if possible, handling special cases like lists and dataclasses."""
    origin, args = get_origin(t), get_args(t)
    # unwrap list[X] so each element can be coerced individually
    if origin is list and args and isinstance(value, list):
        return [coerce_type(v, args[0]) for v in value]
    # convert plain dicts into dataclass instances before typeguard sees them
    if dataclasses.is_dataclass(t) and isinstance(t, type) and isinstance(value, dict):
        return dacite.from_dict(t, value, config=dacite.Config(strict=True))
    return value


def check_type(value: Any, expected_type: type) -> bool:
    """Wrapper around typeguard's check_type that returns a boolean instead of raising an error."""
    try:
        _coerceed_value = coerce_type(value, expected_type)
    except dacite.DaciteError:
        return False
    try:
        _check_type(_coerceed_value, expected_type)
    except TypeCheckError:
        return False

    return True


def pretty_type(type_obj) -> str:
    if origin := get_origin(type_obj):
        if origin is Union:
            # Handle Union types
            types = get_args(type_obj)
            return f"Union[{', '.join(pretty_type(t) for t in types)}]"

    # Handle other generic types if needed, e.g., List, Dict
    elif hasattr(type_obj, "__name__"):
        return type_obj.__name__

    return str(type_obj)


_CAMEL_TO_SNAKE_PAT1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_PAT2 = re.compile(r"([a-z0-9])([A-Z])")


def camel_case_to_snake_case(s: str) -> str:
    """Converts a camelCase or PascalCase string to snake_case."""
    step1 = _CAMEL_TO_SNAKE_PAT1.sub(r"\1_\2", s)
    return _CAMEL_TO_SNAKE_PAT2.sub(r"\1_\2", step1).lower()


def ticks(period: str | int) -> int:
    """Converts a period string (e.g., "1s", "50t") to ticks (1s = 20t)."""
    if type(period) is int:
        return period

    match = re.match(r"(\d+)(t|s|m|d)", period)
    if not match:
        raise ValueError(f"Invalid period format: {period}")

    value, unit = match.groups()
    value = int(value)

    match unit:
        case "t":
            return value
        case "s":
            return value * 20
        case "m":
            return value * 20 * 60
        case "d":
            return value * 24000

    raise ValueError(f"Unknown time unit: {unit}")


def path_to_string(path: str) -> str:
    return path.replace(":", "_").replace("/", "_")


# def color_to_int(color: str) -> int:
#     """Alpha<<24 + Red<<16 + Green<<8 + Blue"""
#         color = color.removeprefix("#")
#         if len(color) == 8:
#             color = color[:6]  # handles VSCode auto-picker adding transparency
#         elif len(color) != 6:
#             raise CustomComponentError(
#                 "Color needs to be in form '#aabbcc' (received: '{color}')",
#                 "dyed_color",
#                 self,
#             )
#         return int(color, 16)
