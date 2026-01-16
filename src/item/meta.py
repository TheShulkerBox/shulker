import copy
import dataclasses
import json
from typing import Any, ClassVar, Self
from itertools import chain, count

from beet import Context
from bolt import Runtime

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
)
from lib.component_validation import McdocValidator, SchemaFile
from lib.rich import console, Tree, Syntax, Group, Panel, RenderableType, Text


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

    # monkeypatched in base.bolt
    ctx: ClassVar[Context]

    _namespace: dict[str, Any]

    def __new__(cls, name: str, bases: list[type], namespace: dict[str, Any]):
        if name == "item":
            return super().__new__(cls, name, bases, namespace)

        namespace["_component_cache"] = {}
        namespace["_has_errored"] = False
        namespace["_components"] = {}

        cls.registered_items[name] = new_cls = super().__new__(
            cls, name, bases, namespace
        )
        new_cls.build()
        return new_cls

    @classmethod
    def validate_component(
        cls, component_name: str, component: dict[str, Any]
    ) -> ComponentError | None:
        if "custom_data" in component_name:
            return

        mcdoc_validator = cls.ctx.inject(McdocValidator)

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

        return NonExistentComponentError(component_name)

    def handle_custom_components(
        self, custom_components: list[Component], resolved_components: dict[str, Any]
    ) -> tuple[list[Component], list[CustomComponentError]]:
        errors = []
        constructed_components = []
        for component in custom_components:
            name: str = component.name()

            try:
                if (data := resolved_components.get(name)) is not None:
                    # remove even if errors to avoid additional validation errors
                    del resolved_components[name]

                    if name not in self._component_cache:
                        field_errors: list[ValidationError] = []
                        reconstructed_data = {}
                        component_fields = {
                            field.name: field
                            for field in dataclasses.fields(component)
                            if field.name not in ("item", "resolved_components")
                        }

                        # validate the fields
                        for field in component_fields.values():
                            if check_type(data, field.type):
                                reconstructed_data[field.name] = data
                                continue

                            if check_type(data, dict):
                                if (value := data.get(field.name)) is None:
                                    if field.default is not dataclasses.MISSING:
                                        reconstructed_data[field.name] = field.default
                                    elif (
                                        field.default_factory is not dataclasses.MISSING
                                    ):
                                        reconstructed_data[field.name] = (
                                            field.default_factory()
                                        )
                                    else:
                                        field_errors.append(
                                            MissingValidationError(
                                                field.name, None, field.type
                                            )
                                        )
                                elif not check_type(value, field.type):
                                    field_errors.append(
                                        ValidationError(field.name, value, field.type)
                                    )
                                else:
                                    reconstructed_data[field.name] = value

                        if unexpected_keys := set(data.keys()) ^ set(
                            reconstructed_data.keys()
                        ):
                            for key in unexpected_keys:
                                if key not in component_fields:
                                    field_errors.append(
                                        UnexpectedValidationError(key, data[key])
                                    )

                        # product error if found
                        if field_errors:
                            raise ComponentError(name, data, field_errors)

                        # attempt to calculate component
                        try:
                            constructed_component = component(
                                item=self,
                                resolved_components=dict(resolved_components),
                                **reconstructed_data,
                            )
                            output = constructed_component.render()
                            constructed_components.append(constructed_component)
                        except Exception as err:
                            # breakpoint()
                            raise ComponentError(name, data, [err])

                        if not component._skip_cache:
                            self._component_cache[name] = output
                    else:
                        output = self._component_cache[name]

                    # if output, deeply merge with custom components
                    if output is not None:
                        metadata = {"custom_components": {name: data}}
                        resolved_components["custom_data"] = deep_merge_dicts(
                            resolved_components["custom_data"], metadata
                        )
                        deep_merge_dicts(resolved_components, output, inplace=True)

            except ComponentError as err:
                errors.append(err)

        return constructed_components, errors

    def handle_custom_transformers(
        self,
        custom_transformers: list[Transformer],
        resolved_components: dict[str, Any],
    ) -> tuple[list[Transformer], list[CustomComponentError]]:
        errors = []
        constructed_transformers = []
        for transformer in custom_transformers:
            name: str = transformer.name()

            try:
                if (data := resolved_components.get(name)) is not None:
                    # remove even if errors to avoid additional validation errors
                    del resolved_components[name]

                    field_errors: list[ValidationError] = []
                    reconstructed_data = {}

                    # validate the fields
                    for field in dataclasses.fields(transformer):
                        if field.name in ("item", "resolved_components"):
                            continue

                        if check_type(data, field.type):
                            reconstructed_data[field.name] = data
                            continue

                        if check_type(data, dict):
                            if (value := data.get(field.name)) is None:
                                if (
                                    field.default is dataclasses.MISSING
                                    and field.default_factory is dataclasses.MISSING
                                ):
                                    field_errors.append(
                                        MissingValidationError(
                                            field.name, None, field.type
                                        )
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
                        constructed_transformer = transformer(
                            item=self,
                            resolved_components=dict(resolved_components),
                            **reconstructed_data,
                        )
                        if (value := constructed_transformer.render()) is not None:
                            resolved_components[name] = value
                        constructed_transformers.append(constructed_transformer)
                    except Exception as err:
                        raise ComponentError(name, data, [err])

            except ComponentError as err:
                errors.append(err)

        return constructed_transformers, errors

    @property
    def components(self) -> dict[str, Any]:
        if self._components:
            return self._components

        original_components = {}

        # Split namespace into callable and non-callable members
        for member in dir(self):
            if member.startswith("_"):
                continue

            if (val := getattr(self, member)) is not None:
                if not callable(val):
                    original_components[member] = copy.deepcopy(val)

        # inject custom data
        output_components = deep_merge_dicts(
            original_components, {"custom_data": {"item_id": self.name}}, inplace=False
        )

        custom_components, component_errors = self.handle_custom_components(
            Component.registered, output_components
        )
        custom_transformers, transformer_errors = self.handle_custom_transformers(
            Transformer.registered, output_components
        )

        if "id" in output_components:
            self.id = output_components.pop("id")

        if "count" in output_components:
            self.count = output_components.pop("count")

        for component_or_transformer in chain(custom_components, custom_transformers):
            if component_or_transformer.name() in original_components:
                component_or_transformer.post_render(output_components)

        if not self._has_errored:
            self._has_errored = self.calculate_errors(
                component_errors,
                transformer_errors,
                output_components,
                original_components,
            )

        self._components = output_components

        return output_components

    def calculate_errors(
        self,
        component_errors: list[CustomComponentError],
        transformer_errors: list[CustomTransformerError],
        output_components: dict[str, Any],
        original_components: dict[str, Any],
    ) -> bool:
        errors: list[ComponentError] = component_errors + transformer_errors

        def handle_suberrors(tree: Tree, suberrors: list[ValidationError | Exception]):
            for suberror in suberrors:
                match suberror:
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
            messages: list[RenderableType] = [Text("⚠️  Item errors", style="header")]
            for error in errors:
                match error:
                    case NonExistentComponentError(name=name):
                        messages.append(f"Component [x]{name!r}[/x] does not exist!")
                    case ComponentError(
                        name=name, component=component, suberrors=suberrors
                    ):
                        tree = Tree(
                            Group(
                                f"Component [x]{name!r}[/x] failed validation",
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

            # messages.append("")
            # messages.append(Text("Original components", style="header"))
            # messages.append(
            #     Syntax(
            #         json.dumps(original_components, indent=2),
            #         "python",
            #         theme="material",
            #     )
            # )

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
            )

            return True
        return False

    @property
    def name(self):
        return camel_case_to_snake_case(self.__name__)

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

        runtime = self.ctx.inject(Runtime)

        # generate unique name
        name = (
            "zz_"
            + runtime.get_nested_location().split("/").pop()
            + f"_{next(self.counter)}"
        )

        return type(name, (self,), kwargs)
