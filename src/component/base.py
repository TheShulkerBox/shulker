from typing import Any, ClassVar, Self, TYPE_CHECKING
from dataclasses import dataclass, field

from lib.helpers import camel_case_to_snake_case

if TYPE_CHECKING:
    from item.meta import ItemType


@dataclass
class Component:
    registered: ClassVar[list[Self]] = []

    item: "ItemType" = field(kw_only=True)
    resolved_components: dict[str, Any] = field(kw_only=True)
    
    def __init_subclass__(cls, cache: bool = True):
        cls._skip_cache = not cache
        new_cls = dataclass(cls)
        new_cls.__module__ = cls.__module__
        cls.registered.append(new_cls)
        return new_cls
    
    @classmethod
    def name(cls) -> str:
        return camel_case_to_snake_case(cls.__name__)
    
    def render(self) -> Any | None:
        raise NotImplementedError

    def post_render(self, resolved_components: dict[str, Any]) -> None:
        ...


@dataclass
class Transformer:
    registered: ClassVar[list[Self]] = []

    item: "ItemType" = field(kw_only=True)
    resolved_components: dict[str, Any] = field(kw_only=True)

    def __init_subclass__(cls):
        new_cls = dataclass(cls)
        new_cls.__module__ = cls.__module__
        cls.registered.append(new_cls)
        return new_cls
    
    @classmethod
    def name(cls) -> str:
        return camel_case_to_snake_case(cls.__name__)
    
    def render(self) -> Any | None:
        raise NotImplementedError

    def post_render(self, resolved_components: dict[str, Any]) -> None:
        ...
