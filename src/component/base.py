from typing import Any, Callable, Protocol, overload
from dataclasses import dataclass

custom_components = []
custom_transformers = []


class Component(Protocol):
    def render(self) -> dict[str, Any]: ...
    def post_render(self) -> None: ...


class Transformer(Protocol):
    def render(self) -> Any | None: ...
    def post_render(self) -> None: ...


@overload
def component(cls: type) -> type: ...


@overload
def component(cache: bool = True) -> Callable[[type], type]: ...


def component(cls: type | None = None, /, *, cache: bool = True):
    def wrap(cls: type):
        cls = dataclass(cls)
        cls.__module__ = cls.__module__
        if not hasattr(cls, "post_render"):
            cls.post_render = lambda *args, **kwargs: None
        cls._cache = cache
        custom_components.append(cls)
        return cls

    # See if we're being called as @component or @component().
    if cls is None:
        # We're called with parens.
        return wrap

    # We're called as @dataclass without parens.
    return wrap(cls)


def transformer(cls: type) -> type:
    cls = dataclass(cls)
    cls.__module__ = cls.__module__
    if not hasattr(cls, "post_render"):
        cls.post_render = lambda *args, **kwargs: None
    custom_transformers.append(cls)
    return cls
