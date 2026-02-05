"""Item system metaclass and component resolution logic.

This module contains our item abstraction layer: a custom class-based syntax for
defining items. Declaratively define items via classes by composing both
vanilla and custom components to build complex items with ease.
"""

import copy
import dataclasses
import json
from typing import Any, ClassVar, Self
from itertools import chain, count

from beet import Context
from bolt import Runtime
import difflib
import pprint

from component.base import Component, Transformer
from lib.helpers import (
    camel_case_to_snake_case,
    nbt_dump,
    deep_merge_dicts,
    check_type,
    pretty_type,
)
from lib.errors import (
    ComponentError,
    CustomTransformerError,
    NonExistentComponentError,
    UnexpectedValidationError,
    ValidationError,
    ItemError,
    CustomComponentError,
    MissingValidationError,
    ComponentTypeError,
)
from lib.component_validation import McdocValidator, SchemaFile
from lib.rich import console, Tree, Syntax, Group, Panel, RenderableType, Text


class ItemType(type):
    """Item system metaclass and component resolution logic.

    This metaclass contains our item abstraction layer: a custom class-based syntax for
    defining items. Declaratively define items via classes by composing both
    vanilla and custom components to build complex items with ease.

    ## Architecture

    We use metaclasses here to help scaffold class definitions into a psuedo-object oriented
    system. The `ItemType` metaclass powers the item system by transforming class definitions
    into item objects with validated components.

    ## Pipeline

    1. **Discovery**: Find all component definitions on the class and track their sources.
    2. **Processing**: Apply custom components and transformers to the relevant component data.
    3. **Validation**: Check all components against schemas.
        a) Vanilla schemas are pulled from mcdoc in src/lib/component_validation.py.
    4. **Caching**: Optionally cache component to avoid recomputation.

    ## Error Handling

    Throughout the pipeline, we gather detailed information related to source location, comparison
    to our schemas, and more to produce rich error messages. We avoid actually crashing `beet` so
    that new versions that may update component schemas don't prevent the build process from
    interrupting.

    ### Details include

    - Source location (class, module, line)
    - "Did you mean?" suggestions for typos
        - Using fuzzy matching via `difflib`
    - Validation details with nested error trees
    - Actionable hints for common mistakes

    ## Usage

    See docs/ITEM_SYSTEM.md for detailed documentation and examples.

    Quick example:

        class MyItem(Item):
            id = "stone"
            item_name = "My Custom Item"
            on_use = {callback: ~/my_function, cooldown: 20}

        # Debug the item
        MyItem.debug()

        # Create variants (anonymous named items)
        variant = MyItem(item_name="Variant", cooldown=10)
    """

    registered_items: ClassVar[dict[str, "ItemType"]] = {}
    counter: ClassVar[count] = count()

    # monkeypatched in base.bolt
    ctx: ClassVar[Context]

    _namespace: dict[str, Any]

    def __new__(cls, name: str, bases: list[type], namespace: dict[str, Any]):
        # Skip base Item class as it's not designed to be actually in-game
        if name == "item":
            return super().__new__(cls, name, bases, namespace)

        namespace["_component_cache"] = {}
        namespace["_has_errored"] = False
        namespace["_components"] = {}
        namespace["_component_sources"] = {}

        cls.registered_items[name] = new_cls = super().__new__(
            cls, name, bases, namespace
        )
        new_cls.build()
        return new_cls

    @staticmethod
    def _validate_dataclass_fields(
        data: Any,
        fields: list,
    ) -> tuple[dict[str, Any], list[ValidationError]]:
        """Validate and reconstruct data according to dataclass field definitions.

        This helper extracts common validation logic used by both custom components
        and transformers. It validates the input data against dataclass field types
        and handles defaults, missing fields, and unexpected keys.

        Args:
            data: The raw data to validate (can be any type)
            fields: List of dataclass fields to validate against

        Returns:
            Tuple of (reconstructed_data, field_errors)
        """
        field_errors: list[ValidationError] = []
        reconstructed_data = {}

        # Build field lookup for easier access
        field_map = {field.name: field for field in fields}

        # Early type check: if we have multiple fields and data is not a dict,
        # check if data matches any single field type. If not, this is likely
        # a type error at the component level.
        if len(fields) > 1 and not check_type(data, dict):
            # Check if data matches any single field type
            matches_any_field = any(check_type(data, field.type) for field in fields)

            # If data doesn't match any field type and we need a dict, report type error
            if not matches_any_field:
                # Count how many fields are required (no default)
                required_fields = [
                    f
                    for f in fields
                    if f.default is dataclasses.MISSING
                    and f.default_factory is dataclasses.MISSING
                ]

                # If we have required fields, this is definitely a type error
                if required_fields:
                    field_errors.append(
                        ComponentTypeError(
                            "component",
                            data,
                            dict,
                            type(data),
                        )
                    )
                    return reconstructed_data, field_errors

        # Handle simple case: data itself matches a field type
        for field in fields:
            if check_type(data, field.type):
                reconstructed_data[field.name] = data
                continue

            # Handle dict case: validate each field
            if check_type(data, dict):
                if (value := data.get(field.name)) is None:
                    # Check if field has a default value
                    if field.default is not dataclasses.MISSING:
                        reconstructed_data[field.name] = field.default
                    elif field.default_factory is not dataclasses.MISSING:
                        reconstructed_data[field.name] = field.default_factory()
                    else:
                        field_errors.append(
                            MissingValidationError(field.name, None, field.type)
                        )
                elif not check_type(value, field.type):
                    field_errors.append(ValidationError(field.name, value, field.type))
                else:
                    reconstructed_data[field.name] = value

        # Check for unexpected keys (only for dict data)
        if check_type(data, dict):
            unexpected_keys = set(data.keys()) - set(reconstructed_data.keys())
            for key in unexpected_keys:
                if key not in field_map:
                    field_errors.append(UnexpectedValidationError(key, data[key]))

        return reconstructed_data, field_errors

    @classmethod
    def validate_component(
        cls, component_name: str, component: dict[str, Any]
    ) -> ComponentError | None:
        """Validate a component against its mcdoc schema.

        Args:
            component_name: Name of the component (e.g., "minecraft:item_name")
            component: Component value to validate

        Returns:
            ComponentError if validation fails, None if valid
        """
        # custom_data has no schema
        if "custom_data" in component_name:
            return

        mcdoc_validator = cls.ctx.inject(McdocValidator)

        # we get a cached schema from lib:component_validation
        schemas: SchemaFile = cls.ctx.meta["item_component_schemas"]
        if (schema := schemas.get(component_name)) is not None:
            if "custom_data" not in component_name:
                try:
                    mcdoc_validator.validate_data(
                        component,
                        schema,
                        [component_name],
                    )
                except ValidationError as err:
                    return ComponentError(component_name, component, [err])
                except ExceptionGroup as err:
                    return ComponentError(
                        component_name, component, err.exceptions, msg=err.args[0]
                    )

                return

        # Component doesn't exist, suggest alternatives
        suggestions = difflib.get_close_matches(
            component_name, schemas.keys(), n=3, cutoff=0.6
        )
        return NonExistentComponentError(component_name, suggestions=suggestions)

    def handle_custom_components(
        self, custom_components: list[Component], resolved_components: dict[str, Any]
    ) -> tuple[list[Component], list[CustomComponentError]]:
        """Process custom components and transform them into vanilla components.

        Custom components are high-level abstractions that render into one or more
        vanilla Minecraft components. This method:
        1. Validates component field types
        2. Instantiates the component dataclass
        3. Calls render() to get vanilla component output
        4. Merges output into resolved_components
        5. Tracks component in custom_data for runtime access

        Args:
            custom_components: List of registered Component classes
            resolved_components: Dict of components being built (modified in-place)

        Returns:
            Tuple of (constructed_components, errors)
        """
        errors = []
        constructed_components = []

        for component in custom_components:
            name: str = component.name()

            try:
                # Check if this component is used in the item definition
                if (data := resolved_components.get(name)) is None:
                    continue

                # Remove from resolved_components to avoid schema validation errors
                # (custom components aren't in the vanilla schema)
                del resolved_components[name]

                # Use cache if available and caching is enabled
                if name in self._component_cache:
                    output = self._component_cache[name]
                else:
                    # Validate fields and reconstruct data
                    component_fields = [
                        field
                        for field in dataclasses.fields(component)
                        if field.name not in ("item", "resolved_components")
                    ]
                    reconstructed_data, field_errors = self._validate_dataclass_fields(
                        data, component_fields
                    )

                    # Raise validation error if fields are invalid
                    if field_errors:
                        raise ComponentError(name, data, field_errors)

                    # Attempt to instantiate and render the component
                    try:
                        constructed_component = component(
                            item=self,
                            resolved_components=dict(resolved_components),
                            **reconstructed_data,
                        )
                        output = constructed_component.render()
                        constructed_components.append(constructed_component)
                    except Exception as err:
                        source_info = self._component_sources.get(name)
                        raise ComponentError(
                            name,
                            data,
                            [err],
                            hint=f"Error while rendering custom component '{name}' in item '{self.name}'",
                            source_info=source_info,
                        ) from err

                    # Cache output if caching is enabled
                    if not component._skip_cache:
                        self._component_cache[name] = output

                # Merge component output into resolved_components
                if output is not None:
                    # Track original component data in custom_data for runtime access
                    metadata = {"custom_components": {name: data}}
                    resolved_components["custom_data"] = deep_merge_dicts(
                        resolved_components.get("custom_data", {}), metadata
                    )
                    # Merge rendered vanilla components
                    deep_merge_dicts(resolved_components, output, inplace=True)

            except ComponentError as err:
                errors.append(err)

        return constructed_components, errors

    def handle_custom_transformers(
        self,
        custom_transformers: list[Transformer],
        resolved_components: dict[str, Any],
    ) -> tuple[list[Transformer], list[CustomComponentError]]:
        """Process custom transformers that modify component values.

        Transformers take a component value and transform it into a different form.
        For example, a color transformer might convert "#ff0000" to 16711680.

        Unlike components which create new vanilla components, transformers modify
        the value of an existing component in-place.

        Args:
            custom_transformers: List of registered Transformer classes
            resolved_components: Dict of components being built (modified in-place)

        Returns:
            Tuple of (constructed_transformers, errors)
        """
        errors = []
        constructed_transformers = []

        for transformer in custom_transformers:
            name: str = transformer.name()

            try:
                # Check if this transformer applies to a component in the item
                if (data := resolved_components.get(name)) is None:
                    continue

                # Temporarily remove to avoid schema validation on untransformed value
                del resolved_components[name]

                # Validate transformer fields
                transformer_fields = [
                    field
                    for field in dataclasses.fields(transformer)
                    if field.name not in ("item", "resolved_components")
                ]
                reconstructed_data, field_errors = self._validate_dataclass_fields(
                    data, transformer_fields
                )

                # Raise validation error if fields are invalid
                if field_errors:
                    raise ComponentError(name, data, field_errors)

                # Attempt to instantiate and render the transformer
                try:
                    constructed_transformer = transformer(
                        item=self,
                        resolved_components=dict(resolved_components),
                        **reconstructed_data,
                    )
                    # Only update component if transformer returns a value
                    if (
                        transformed_value := constructed_transformer.render()
                    ) is not None:
                        resolved_components[name] = transformed_value
                    constructed_transformers.append(constructed_transformer)
                except Exception as err:
                    source_info = self._component_sources.get(name)
                    raise ComponentError(
                        name,
                        data,
                        [err],
                        hint=f"Error while rendering custom transformer '{name}' in item '{self.name}'",
                        source_info=source_info,
                    ) from err

            except ComponentError as err:
                errors.append(err)

        return constructed_transformers, errors

    @property
    def components(self) -> dict[str, Any]:
        """Lazy property that discovers, resolves, and validates all item components.

        This is the main entry point for component resolution. It performs these steps:
        1. **Discovery**: Find all component definitions via introspection.
        2. **Source Tracking**: Record where each component was defined for errors.
        3. **Processing**: Apply custom components and transformers.
        4. **Validation**: Check all components against mcdoc schemas.
        5. **Caching**: Store results for future access.

        The property is lazy - components are only resolved on first access and then
        cached for subsequent calls.

        Returns:
            Dict of resolved vanilla Minecraft components
        """
        # Return cached components if available
        if self._components:
            return self._components

        # Phase 1: Discovery - find all component definitions
        original_components = {}
        for member in dir(self):
            # Skip private members and callables
            if member.startswith("_"):
                continue

            if (val := getattr(self, member)) is not None:
                if not callable(val):
                    # Deep copy to prevent mutations
                    original_components[member] = copy.deepcopy(val)

                    # Track source for error messages
                    self._component_sources[member] = {
                        "class": self.__name__,
                        "module": self.__module__,
                        "original_value": val,
                    }

        # Phase 2: Initialize with item metadata
        output_components = deep_merge_dicts(
            original_components, {"custom_data": {"item_id": self.name}}, inplace=False
        )

        # Phase 3: Apply custom components and transformers
        custom_components, component_errors = self.handle_custom_components(
            Component.registered, output_components
        )
        custom_transformers, transformer_errors = self.handle_custom_transformers(
            Transformer.registered, output_components
        )

        # Phase 4: Extract special fields (id and count aren't component data)
        if "id" in output_components:
            self.id = output_components.pop("id")

        if "count" in output_components:
            self.count = output_components.pop("count")

        # Phase 5: Allow components/transformers to post-process
        for component_or_transformer in chain(custom_components, custom_transformers):
            if component_or_transformer.name() in original_components:
                component_or_transformer.post_render(output_components)

        # Phase 6: Validate and collect errors
        if not self._has_errored:
            self._has_errored = self.calculate_errors(
                component_errors,
                transformer_errors,
                output_components,
                original_components,
            )

        # Phase 7: Cache and return
        self._components = output_components
        return output_components

    def format_error_summary(self, errors: list[ComponentError]) -> str:
        """Generate a one-line summary of all errors"""
        summaries = []
        for error in errors:
            match error:
                case NonExistentComponentError(name=name):
                    summaries.append(f"{name}: doesn't exist")
                case ComponentError(name=name, suberrors=suberrors):
                    # Count error types
                    type_errors = sum(
                        1 for e in suberrors if isinstance(e, ComponentTypeError)
                    )
                    missing = sum(
                        1 for e in suberrors if isinstance(e, MissingValidationError)
                    )
                    wrong_type = sum(
                        1
                        for e in suberrors
                        if isinstance(e, ValidationError)
                        and not isinstance(
                            e,
                            (
                                MissingValidationError,
                                UnexpectedValidationError,
                                ComponentTypeError,
                            ),
                        )
                    )
                    unexpected = sum(
                        1 for e in suberrors if isinstance(e, UnexpectedValidationError)
                    )
                    other = (
                        len(suberrors) - missing - wrong_type - unexpected - type_errors
                    )

                    parts = []
                    if type_errors:
                        parts.append("wrong type")
                    if missing:
                        parts.append(f"{missing} missing")
                    if wrong_type:
                        parts.append(f"{wrong_type} wrong field type")
                    if unexpected:
                        parts.append(f"{unexpected} unexpected")
                    if other:
                        parts.append(f"{other} other")

                    summaries.append(f"{name}: {', '.join(parts)}")

        return " | ".join(summaries) if summaries else "unknown errors"

    def calculate_errors(
        self,
        component_errors: list[CustomComponentError],
        transformer_errors: list[CustomTransformerError],
        output_components: dict[str, Any],
        original_components: dict[str, Any],
    ) -> bool:
        """Validate components and display comprehensive error messages.

        This method:
        1. Validates all output components against mcdoc schemas
        2. Collects all errors (custom component, transformer, and validation)
        3. Formats and displays errors with rich context (source, hints, suggestions)

        Args:
            component_errors: Errors from custom component processing
            transformer_errors: Errors from transformer processing
            output_components: Final resolved components to validate
            original_components: Original component definitions (for debugging)

        Returns:
            True if any errors were found, False otherwise
        """
        errors: list[ComponentError] = component_errors + transformer_errors

        def handle_suberrors(tree: Tree, suberrors: list[ValidationError | Exception]):
            """Recursively render validation errors in a tree structure."""
            for suberror in suberrors:
                match suberror:
                    case ComponentTypeError(
                        expected=expected,
                        actual_type=actual_type,
                    ):
                        tree.add(
                            f"[red]Wrong type:[/red] Expected [x]{pretty_type(expected)!r}[/x] but got [x]{pretty_type(actual_type)!r}[/x]"
                        )
                        tree.add(
                            f"[yellow]💡 Hint:[/yellow] This component should be a dictionary with multiple fields, not a {pretty_type(actual_type)}"
                        )
                    case UnexpectedValidationError(
                        name=name,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        tree.add(f"Unexpected field [x]{name!r}[/x]{msg}")
                    case MissingValidationError(
                        name=name,
                        expected=expected,
                        suberrors=suberrors,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        tree.add(
                            f"Missing field [x]{name!r}[/x] (expected type [x]{pretty_type(expected)!r}[/x]){msg}"
                        )
                    case ValidationError(
                        name=name,
                        expected=expected,
                        suberrors=suberrors,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        subtree = tree.add(
                            f"Expected [x]{name!r}[/x] as type [x]{pretty_type(expected)!r}[/x]{msg}"
                        )
                        handle_suberrors(subtree, suberrors)
                    case RecursionError() as err:
                        raise err
                    case ExceptionGroup(exceptions=errors) as err:
                        subtree = tree.add(err.args[0])
                        handle_suberrors(subtree, errors)
                    case err:
                        tree.add(f"[x]{pretty_type(type(err))}[/x]: {err.args[0]}")

        for name, component in output_components.items():
            if error := self.validate_component(name, component):
                errors.append(error)

        if errors:
            messages: list[RenderableType] = [
                Text("⚠️  Item errors", style="header"),
                Text(f"❌ {self.format_error_summary(errors)}", style="red"),
                "",
            ]
            for error in errors:
                match error:
                    case NonExistentComponentError(name=name, suggestions=suggestions):
                        msg_parts = [f"Component [x]{name!r}[/x] does not exist!"]
                        if suggestions:
                            msg_parts.append(
                                f"  [dim]Did you mean:[/dim] {', '.join(f'[green]{s}[/green]' for s in suggestions)}"
                            )
                        if source_info := self._component_sources.get(name):
                            msg_parts.append(
                                f"  [dim]Defined in:[/dim] {source_info['class']} ({source_info['module']})"
                            )
                        messages.append("\n".join(msg_parts))
                    case ComponentError(
                        name=name,
                        component=component,
                        suberrors=suberrors,
                        hint=hint,
                        source_info=source_info,
                    ):
                        header_parts = [f"Component [x]{name!r}[/x] failed validation"]
                        if source_info:
                            header_parts.append(
                                f"[dim]Defined in:[/dim] {source_info['class']} ({source_info['module']})"
                            )
                        if hint:
                            header_parts.append(f"[yellow]💡 {hint}[/yellow]")

                        tree = Tree(
                            Group(
                                *header_parts,
                                Syntax(
                                    json.dumps(component, indent=2),
                                    "python",
                                    theme="material",
                                ),
                            ),
                            guide_style="red",
                        )

                        handle_suberrors(tree, suberrors)
                        messages.append(tree)

            title = f"Item [x]{self.name!r}[/x] failed component validation"
            subtitle = Text(self.__module__, style="secondary")
            console.print(
                Panel(
                    Group(*messages),
                    title=title,
                    subtitle=subtitle,
                    highlight=True,
                ),
                highlight=True,
                expand=False,
            )

            return True
        return False

    @property
    def name(self) -> str:
        """Get the item's snake_case name from its class name."""
        return camel_case_to_snake_case(self.__name__)

    @property
    def has_id(self) -> bool:
        """Check if this item has a Minecraft ID defined."""
        return self.id is not None

    @property
    def is_generated(self) -> bool:
        """Check if this is a generated item (e.g., from Item(...) calls)."""
        return "generated" in self.name

    @property
    def path(self) -> str:
        """Get the namespaced path for this item."""
        return f"item:{self.name}"

    def item_string(self) -> str:
        """Generate a Minecraft give command string for this item.

        Returns:
            String like "minecraft:stone[item_name='...']"

        Raises:
            ItemError: If item doesn't have an ID defined
        """
        components = ",".join(f"{k}={nbt_dump(v)}" for k, v in self.components.items())
        if not self.has_id:
            raise ItemError(
                f"`{self.name}` item must define an `id` if generating a give or other command!"
            )
        return f"{self.id}[{components}]"

    def conditional_string(self) -> str:
        """Generate a Minecraft item predicate string for conditional checks.

        Used for detecting if a player has this item via custom_data matching.

        Returns:
            String like "*[custom_data~{item_id:'dart'}]"
        """
        id = self.id or "*"
        return f"{id}[custom_data~{{item_id:'{self.name}'}}]"

    def as_dict(self) -> dict[str, Any]:
        """Convert item to a dictionary suitable for NBT serialization."""
        return {"id": self.id, "count": self.count, **self.components}

    __neg__ = __invert__ = conditional_string
    __pos__ = __str__ = item_string

    def debug(self):
        """Display comprehensive debugging information about this item's construction.

        Shows:
        - Item name and module location
        - Original component definitions (before transformation)
        - Which custom components/transformers were applied
        - Final resolved vanilla components

        Usage:
            MyItem.debug()  # Print debug info to console

        This is helpful when:
        - Debugging component validation errors
        - Understanding how custom components transform
        - Verifying final component values
        """
        # Collect custom components/transformers that apply to this item
        item_attrs = {k for k in self.__dict__.keys() if not k.startswith("_")}
        applied_components = [
            f"  • {comp.name()} → {comp.__name__}"
            for comp in Component.registered
            if comp.name() in item_attrs
        ]
        applied_transformers = [
            f"  • {trans.name()} (transformer) → {trans.__name__}"
            for trans in Transformer.registered
            if trans.name() in item_attrs
        ]

        # Build the display
        content_parts = [
            Text(f"Item: {self.name}", style="bold blue"),
            Text(f"Module: {self.__module__}", style="dim"),
            Text(f"ID: {self.id if self.has_id else '[not set]'}", style="dim"),
            "",
            Text("Original attributes:", style="bold"),
            Syntax(
                pprint.pformat(
                    {
                        k: v
                        for k, v in self.__dict__.items()
                        if not k.startswith("_") and not callable(v)
                    }
                ),
                "python",
                theme="material",
            ),
        ]

        # Add custom components section if any apply
        if applied_components or applied_transformers:
            content_parts.extend(
                [
                    "",
                    Text("Custom components/transformers:", style="bold"),
                    *[Text(line) for line in applied_components + applied_transformers],
                ]
            )

        # Add final components
        content_parts.extend(
            [
                "",
                Text("Final components:", style="bold"),
                Syntax(
                    pprint.pformat(self.components),
                    "python",
                    theme="material",
                ),
            ]
        )

        console.print(
            Panel(
                Group(*content_parts),
                title=f"Debug: {self.name}",
                border_style="blue",
                expand=False,
            )
        )

    def __repr__(self):
        fields = ", ".join(
            f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("_")
        )
        return f"{self.name}[{fields}]"

    def __call__(self, /, **kwargs) -> Self:
        """Create an anonymous variant of this item with modified components.

        This allows you to create item variations without defining new classes.
        The variant inherits all components from the parent item and overrides
        only the specified ones.

        Args:
            **kwargs: Component overrides (e.g., item_name="Variant", count=5)

        Returns:
            A new anonymous item class with the specified changes

        Raises:
            ItemError: If called without any component changes

        Example:
            # Define base item
            class Sword(Item):
                id = "diamond_sword"
                item_name = "Base Sword"
                damage = 10

            # Create variants
            fire_sword = Sword(item_name="Fire Sword", damage=15)
            ice_sword = Sword(item_name="Ice Sword", damage=12)

        Note:
            Each variant gets a unique generated name to avoid collisions.
            The name is based on the calling location and a counter.
        """
        if not kwargs:
            raise ItemError(f"Cannot instantiate `{self.name}` without changes!")

        runtime = self.ctx.inject(Runtime)

        # Generate unique name based on location and counter
        # Format: zz_<function_name>_<counter>
        name = (
            "zz_"
            + runtime.get_nested_location().split("/").pop()
            + f"_{next(self.counter)}"
        )

        # Create anonymous subclass with overrides
        return type(name, (self,), kwargs)
