"""Base classes for custom components and transformers.

Custom components and transformers are the extension points for the item system.
They allow you to create high-level abstractions that compile down to vanilla
Minecraft components.

## Component vs Transformer

**Components** create new vanilla components:
- Input: User-defined data (e.g., {callback: ~/function, cooldown: 20})
- Output: One or more vanilla components (e.g., minecraft:use_cooldown)
- Example: on_use component → use_cooldown + custom_data

**Transformers** modify existing component values:
- Input: Component value in any format (e.g., "#ff0000")
- Output: Transformed value (e.g., 16711680)
- Example: dyed_color transformer converts hex colors to integers

## Creating Custom Components

Subclass `Component` and define fields for user input:

    @dataclass
    class MyComponent(Component):
        value: str
        enabled: bool = True

        def render(self) -> dict[str, Any] | None:
            if not self.enabled:
                return None

            return {
                "minecraft:custom_data": {
                    "my_component": {"value": self.value}
                }
            }

## Creating Custom Transformers

Subclass `Transformer` and define transformation logic:

    @dataclass
    class HexColor(Transformer):
        color: str | int

        def render(self) -> int | None:
            if isinstance(self.color, int):
                return self.color
            return int(self.color.lstrip('#'), 16)

## Auto-Registration

Both components and transformers auto-register via `__init_subclass__`,
so they're automatically discovered and applied during item resolution.
"""

from typing import Any, ClassVar, Self, TYPE_CHECKING
from dataclasses import dataclass, field
from bolt_expressions import DataSource

from lib.helpers import camel_case_to_snake_case

if TYPE_CHECKING:
    from item.type import ItemType


@dataclass
class Component:
    """Base class for custom item components.

    Custom components are high-level abstractions that render into vanilla
    Minecraft components. They allow you to encapsulate complex component
    logic behind a simple interface.

    ## Attributes

    - **registered**: Class variable tracking all registered components
    - **item**: The item class this component is being applied to
    - **resolved_components**: All components resolved so far (for context)

    ## Subclassing

    1. Define fields for user input (with type hints)
    2. Implement `build()` to return vanilla components
    3. Optionally implement `post_build()` for cleanup

    ## Caching

    By default, component output is cached. To disable caching:

        class MyComponent(Component, cache=False):
            ...

    This is useful for components that depend on runtime state.
    """

    registered: ClassVar[list[Self]] = []

    item: "ItemType" = field(kw_only=True)
    resolved_components: dict[str, Any] = field(kw_only=True)

    def __init_subclass__(cls, cache: bool = True, base_type: type = None):
        """Auto-register component and convert to dataclass."""
        cls._skip_cache = not cache
        cls._base_type = base_type if base_type is not None else None
        new_cls = dataclass(cls)
        new_cls.__module__ = cls.__module__
        cls.registered.append(new_cls)
        return new_cls

    @classmethod
    def name(cls) -> str:
        """Get the snake_case name of this component."""
        return camel_case_to_snake_case(cls.__name__)

    def build(self) -> dict[str, Any] | None:
        """Render this component into vanilla Minecraft components.

        Returns:
            Dict of vanilla components, or None to skip this component

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def post_build(self, resolved_components: dict[str, Any]) -> None:
        """Optional post-processing after all components are resolved.

        Use this to modify resolved_components in-place after rendering.
        This is called only if the component was present in the original
        item definition.

        Args:
            resolved_components: All resolved components (mutable)
        """
    
    def render(self, item_data: DataSource) -> None:
        """Optional runtime rendering"""


@dataclass
class Transformer:
    """Base class for component value transformers.

    Transformers modify the value of an existing component. They're useful
    for providing multiple input formats or preprocessing component values.

    ## Attributes

    - **registered**: Class variable tracking all registered transformers
    - **item**: The item class this transformer is being applied to
    - **resolved_components**: All components resolved so far (for context)

    ## Subclassing

    1. Define fields for accepted input types (with union types if needed)
    2. Implement `render()` to return transformed value
    3. Optionally implement `post_render()` for cleanup

    ## Example

        @dataclass
        class ColorTransformer(Transformer):
            color: str | int  # Accept hex string or integer

            def render(self) -> int:
                if isinstance(self.color, str):
                    return int(self.color.lstrip('#'), 16)
                return self.color

    Then use in items:

        class MyItem(Item):
            dyed_color = "#ff0000"  # Transformed to 16711680
    """

    registered: ClassVar[list[Self]] = []

    item: "ItemType" = field(kw_only=True)
    resolved_components: dict[str, Any] = field(kw_only=True)

    def __init_subclass__(cls):
        """Auto-register transformer and convert to dataclass."""
        new_cls = dataclass(cls)
        new_cls.__module__ = cls.__module__
        cls.registered.append(new_cls)
        return new_cls

    @classmethod
    def name(cls) -> str:
        """Get the snake_case name of this transformer."""
        return camel_case_to_snake_case(cls.__name__)

    def build(self) -> Any | None:
        """Transform the component value.

        Returns:
            Transformed value, or None to leave component unchanged

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def post_build(self, resolved_components: dict[str, Any]) -> None:
        """Optional post-processing after all components are resolved.

        Use this to modify resolved_components in-place after transformation.
        This is called only if the transformer was present in the original
        item definition.

        Args:
            resolved_components: All resolved components (mutable)
        """

    def render(self, item_data: DataSource) -> None:
        """Optional runtime rendering"""
