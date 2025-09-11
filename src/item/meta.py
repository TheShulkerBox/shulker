import copy
import dataclasses
from typing import Any, ClassVar, Self
from itertools import count

from beet import Context
import rich
from rich.pretty import Pretty
from rich.panel import Panel
from rich.console import Group

from component.meta import Component, Transformer
from lib.helpers import title_case_to_snake_case, nbt_dump, deep_merge_dicts, check_type, pretty_type
from lib.errors import (
    ComponentError,
    CustomTransformerError,
    NonExistentComponentError,
    UnexpectedValidationError,
    ValidationError,
    ItemError,
    CustomComponentError,
    MissingValidationError,
)
from lib.component_validation import validate_data, SchemaFile


class ItemType(type):
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

    registered_items: ClassVar[dict[str, "ItemType"]] = {}
    counter: ClassVar[count] = count()

    # monkeypatched in base.bolt (which is auto-generated via plugins.custom_load)
    ctx: ClassVar[Context]

    _namespace: dict[str, Any]

    def __new__(cls, name: str, bases: list[type], namespace: dict[str, Any]):
        if name == "item":
            return super().__new__(cls, name, bases, namespace)

        if name.lower() != name:
            raise ItemError(
                f"item '{name}' should be defined with `snake_case` "
                f"('{title_case_to_snake_case(name)}')."
            )

        namespace["_component_cache"] = {}
        cls.registered_items[name] = new_cls = super().__new__(
            cls, name, bases, namespace
        )
        return new_cls

    @classmethod
    def validate_component(
        cls, component_name: str, component: dict[str, Any]
    ) -> ComponentError | None:
        if "custom_data" in component_name:
            return

        schemas: SchemaFile = cls.ctx.meta["item_component_schemas"]
        if (schema := schemas.get(component_name)) is not None:
            if "custom_data" not in component_name:
                try:
                    validate_data(
                        component,
                        schema,
                        cls.ctx.meta["mcdoc"]["mcdoc"],
                        [component_name],
                    )
                except ValidationError as err:
                    return ComponentError(component_name, component, [err])
                except ExceptionGroup as err:
                    return ComponentError(component_name, component, err.exceptions, msg=err.args[0])
                
                return

        return NonExistentComponentError(component_name)

    def handle_custom_components(
        self, components: list[Component], resolved_components: dict[str, Any]
    ) -> list[CustomComponentError]:
        errors = []
        for component in components:
            name: str = component.__name__

            try:
                if (data := resolved_components.get(name)) is not None:
                    # remove even if errors to avoid additional validation errors
                    del resolved_components[name]

                    if name not in self._component_cache:
                        field_errors: list[ValidationError] = []
                        reconstructed_data = {}

                        # validate the fields
                        for field in dataclasses.fields(component):
                            if check_type(data, field.type):
                                reconstructed_data[field.name] = data
                                continue
                                                    
                            if check_type(data, dict):
                                if (value := data.get(field.name)) is None:
                                    if field.default is not dataclasses.MISSING:
                                        reconstructed_data[field.name] = field.default
                                    elif field.default_factory is not dataclasses.MISSING:
                                        reconstructed_data[field.name] = field.default_factory()
                                    else:
                                        field_errors.append(
                                            MissingValidationError(field.name, None, field.type)
                                        )
                                elif not check_type(value, field.type):
                                    field_errors.append(
                                        ValidationError(field.name, value, field.type)
                                    )
                                else:
                                    reconstructed_data[field.name] = value

                        # product error if found
                        if field_errors:
                            raise ComponentError(name, data, field_errors)

                        # attempt to calculate component
                        try:
                            constructed_component = component(**reconstructed_data)
                            constructed_component.item = self
                            output = constructed_component()
                        except Exception as err:
                            raise ComponentError(name, data, [err])

                        self._component_cache[name] = output
                    else:
                        output = self._component_cache[name]

                    # if output, deeply merge with custom components
                    if output is not None:
                        metadata = {"custom_components": {name: data}}
                        resolved_components["custom_data"] = deep_merge_dicts(
                            resolved_components["custom_data"], metadata
                        )
                        deep_merge_dicts(
                            resolved_components, output, inplace=True
                        )

            except ComponentError as err:
                errors.append(err)

        return errors

    def handle_custom_transformers(
        self, transformers: list[Transformer], resolved_components: dict[str, Any]
    ) -> list[CustomTransformerError]:
        errors = []
        for transformer in transformers:
            name = transformer.__name__

            try:
                if (data := resolved_components.get(name)) is not None:
                    # remove even if errors to avoid additional validation errors
                    del resolved_components[name]

                    field_errors: list[ValidationError] = []
                    reconstructed_data = {}

                    # validate the fields
                    for field in dataclasses.fields(transformer):
                        if check_type(data, field.type):
                            reconstructed_data[field.name] = data
                            continue
                        
                        if check_type(data, dict):
                            if (value := data.get(field.name)) is None:
                                if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                                    field_errors.append(
                                        MissingValidationError(field.name, None, field.type)
                                    )
                            elif not check_type(value, field.type):
                                field_errors.append(
                                    ValidationError(field.name, value, field.type)
                                )

                            reconstructed_data[field.name] = value

                    # produce error if found
                    if field_errors:
                        raise ComponentError(name, data, field_errors)

                    try:
                        constructed_transformer = transformer(**reconstructed_data)
                        constructed_transformer.item = self
                        if (value := constructed_transformer()) is not None:
                            resolved_components[name] = value
                    except Exception as err:
                        raise ComponentError(name, data, [err])

            except ComponentError as err:
                errors.append(err)

        return errors

    @property
    def components(self):
        output_components = {}

        # Split namespace into callable and non-callable members
        for member in dir(self):
            if member.startswith("_"):
                continue

            if (val := getattr(self, member)) is not None:
                if not callable(val):
                    output_components[member] = copy.deepcopy(val)

        # inject custom data
        output_components = deep_merge_dicts(
            output_components, {"custom_data": {"item_id": self.name}}
        )

        component_errors = self.handle_custom_components(
            self._components, output_components
        )
        transformer_errors = self.handle_custom_transformers(
            self._transformers, output_components
        )

        if "id" in output_components:
            self.id = output_components.pop("id")

        if "count" in output_components:
            self.count = output_components.pop("count")

        self.calculate_errors(
            component_errors, transformer_errors, output_components
        )

        return output_components

    def calculate_errors(
        self,
        component_errors: list[CustomComponentError],
        transformer_errors: list[CustomTransformerError],
        output_components: dict[str, Any],
    ) -> bool:
        errors: list[ComponentError] = component_errors + transformer_errors

        def handle_suberrors(
            suberrors: list[ValidationError | Exception], depth: int = 1
        ):
            for suberror in suberrors:
                indent = " " * depth * 3
                match suberror:
                    case UnexpectedValidationError(
                        name=name,
                        value=value,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        yield f"{indent}[bold red]|_[/bold red] Unexpected field [bold green]{name!r}[/bold green] with {value!r}){msg}"
                    case MissingValidationError(
                        name=name,
                        expected=expected,
                        suberrors=suberrors,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        yield f"{indent}[bold red]|_[/bold red] Missing field [bold green]{name!r}[/bold green] (expected type {pretty_type(expected)!r}){msg}"
                    case ValidationError(
                        name=name,
                        value=value,
                        expected=expected,
                        suberrors=suberrors,
                        msg=msg,
                    ):
                        msg = f" ({msg})" if msg else ""
                        yield f"{indent}[bold red]|_[/bold red] Expected [bold green]{name!r}[/bold green] as type {pretty_type(expected)!r} (actual {value!r}){msg}"
                        yield from handle_suberrors(suberrors)
                    case RecursionError() as err:
                        raise err
                    case err:
                        yield f"{indent}[bold red]|_[/bold red] {pretty_type(type(err))}: {err.args[0]}"

        for name, component in output_components.items():
            if error := self.validate_component(name, component):
                errors.append(error)

        if errors:
            messages = []
            messages.append("[bold grey50]Errors:")
            for error in errors:
                match error:
                    case NonExistentComponentError(name=name):
                        messages.append(
                            f"[bold red]|_[/bold red] [bold green]'{name}'[/bold green] component does not exist!"
                        )
                    case ComponentError(name=name, suberrors=suberrors):
                        messages.append(
                            f"[bold red]|_[/bold red] [bold green]'{name}'[/bold green] failed component validation."
                        )
                        messages += list(handle_suberrors(suberrors))

            messages.append("")
            messages.append("[bold grey50]Resolved components:")
            messages.append(Pretty(output_components))

            rich.print(
                Panel(
                    Group(*messages),
                    title=f"[red]Item [bold green]{self.name!r}[/bold green] [italic grey50](from {self.__module__})[/italic grey50] failed component validation.",
                )
            )

            return True
        return False

    @property
    def name(self):
        return self.__name__

    def has_id(self):
        return self.id is not None

    def is_generated(self):
        return "generated" in self.name

    @property
    def path(self):
        return f"item:{self.name}"

    def item_string(self) -> str:
        components = ",".join(f"{k}={nbt_dump(v)}" for k, v in self.components.items())
        if not self.has_id:
            raise ItemError(
                f"`{self.name}` item must define an `id` if generating a give or other command!"
            )
        return f"{self.id}[{components}]"

    def conditional_string(self) -> str:
        id = self.id or "*"
        return f"{id}[custom_data~{{item_id:'{self.name}'}}]"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "count": self.count, **self.components}

    __neg__ = __invert__ = conditional_string
    __pos__ = __str__ = item_string

    def __repr__(self):
        fields = ", ".join(
            f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("_")
        )
        return f"{self.name}[{fields}]"

    def __call__(self, /, **kwargs) -> Self:
        """Returns an anonymous item that inherits from this item with changes from kwargs"""

        if not kwargs:
            raise ItemError(f"Cannot instantiate `{self.name}` without changes!")

        # generate unique name
        name = (
            self.ctx.generate.path(self.name + "_generated_{incr}")
            .replace(":", "_")
            .replace("/", "_")
        )

        return type(name, (self,), kwargs)
