from typing import Any, Protocol
from dataclasses import dataclass

components = []
transformers = []


class Component(Protocol):
    def __call__(self) -> dict[str, Any]: ...


class Transformer(Protocol):
    def __call__(self) -> Any | None: ...


def component(cls: type) -> type:
    cls = dataclass(cls)
    cls.__module__ = cls.__module__
    components.append(cls)
    return cls


def transformer(cls: type) -> type:
    cls = dataclass(cls)
    cls.__module__ = cls.__module__
    transformers.append(cls)
    return cls
