import copy
from inspect import signature, Signature
from typing import Any, ClassVar, Union
from itertools import count

from beet import Context
import rich
from rich.pretty import Pretty
from rich.panel import Panel
from rich.console import Group
from lib.helpers import title_case_to_snake_case, nbt_dump, deep_merge_dicts

from plugins.component_caching import SchemaFile, ValidationError, validate_data


class ItemError(Exception):
    """Exceptions related to custom items"""


class ComponentError(ItemError):
    """An Item Error specific towards custom components and transformers"""

    def __init__(self, name: str, component: Any, signature: Signature):
        super().__init__(
            f"Component `{name}` is invalid: `{type(component)}` (`{component}`).\n"
            "Expected `dict` with schema: \n"
            + "\n".join(
                f"  {name}: {param.annotation}"
                for name, param in signature.parameters.items()
                if name != "self"
            )
        )


class ItemMeta(type):
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

    registered_items: ClassVar[dict[str, "ItemMeta"]] = {}
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
        
        cls.registered_items[name] = new_cls = super().__new__(
            cls, name, bases, namespace
        )
        return new_cls

    @classmethod
    def validate_component(cls, component_name: str, component: dict[str, Any]):
        if "custom_data" in component_name or "count" in component_name:
            return

        schemas: SchemaFile = cls.ctx.meta["item_component_schemas"]
        if (schema := schemas.get(component_name)) is not None:
            if "custom_data" not in component_name:
                validate_data(component, schema, cls.ctx.meta["mcdoc"]["mcdoc"])
                return
        
        raise ValidationError(f"Component [bold green]'{component_name}'[/bold green] is not a vanilla component!")

    @property
    def components(self):
        output_components = {}
        callable_members = {}
        custom_components = []  # to remove later

        # Split namespace into callable and non-callable members
        for member in dir(self):
            if (
                not member.startswith("_")
                and (val := getattr(self, member)) is not None
            ):
                if callable(val):
                    callable_members[member] = val
                else:
                    output_components[member] = copy.deepcopy(val)

        # inject custom data
        output_components = deep_merge_dicts(
            output_components, {"custom_data": {"item_id": self.name}}
        )

        # For each callable member, handle component and transformer
        for k, func in callable_members.items():
            # Custom components return a dictionary containing one or more components
            if (index := k.find("_component")) > 1:
                name = k[:index]
                sig = signature(func)

                # If the component is defined in the item, apply the function
                if component := output_components.get(name):
                    try:
                        # Call the custom component function based on the signature
                        if type(component) is not dict:
                            if len(sig.parameters) > 1:
                                raise ComponentError(name, component, sig)
                            new_namespace = func(component)
                        else:
                            new_namespace = func(**component)

                        # If our result exists, deeply merge our new components
                        # We also inject some metadata
                        if new_namespace is not None:
                            metadata = {"custom_components": {name: component}}
                            output_components["custom_data"] = deep_merge_dicts(
                                output_components["custom_data"], metadata
                            )
                            output_components = deep_merge_dicts(
                                output_components, new_namespace
                            )
                            custom_components.append(name)

                    except Exception as e:
                        raise ComponentError(name, component, sig) from e

            # Transformers modify the value of an existing component
            elif (index := k.find("_transformer")) > 1:
                name = k[:index]

                # If the component exists, apply the transformer function
                if name in output_components:
                    if (value := func(output_components[name])) is not None:
                        output_components[name] = value

        if "id" in output_components:
            self.id = output_components["id"]
        del output_components["id"]

        for component in custom_components:
            if component in output_components:
                del output_components[component]
        
        errors: list[tuple[ExceptionGroup | ValidationError, str, dict[str, Any]]] = []
        for name, component in output_components.items():
            try:
                self.validate_component(name, component)
            except ExceptionGroup as e:
                errors.append((e, name, component))
            except ValidationError as e:
                errors.append((e, name, component))
        
        if errors:
            messages = []
            for error, name, component in errors:
                messages.append("[bold grey50]Errors:")
                match error:
                    case ExceptionGroup(exceptions=exceptions):
                        messages.append(f"[bold red]|_[/bold red] Component [bold green]'{name}'[/bold green] failed validation.")
                        for suberror in exceptions:
                            messages.append(f"  [bold red]|_[/bold red] {suberror.args[0]}")
                    case ValidationError() as err:
                        messages.append(f"[bold red]|_[/bold red] {err.args[0]}")
                messages.append("")
                messages.append("[bold grey50]Resolved components:")
                messages.append(Pretty(output_components))
            rich.print(Panel(Group(*messages), title=f"[red]Item [bold green]{self.name!r}[/bold green] [italic grey50](from {self.__module__})[/italic grey50] failed component validation."))

        return output_components

    @property
    def name(self):
        return self.__name__

    @property
    def has_id(self):
        return self.id is not None

    def item_string(self):
        components = ",".join(f"{k}={nbt_dump(v)}" for k, v in self.components.items())
        if not self.has_id:
            raise ItemError(
                f"`{self.name}` item must define an `id` if generating a give or other command!"
            )
        return f"{self.id}[{components}]"

    def conditional_string(self):
        id = self.id or "*"
        return f"{id}[custom_data~{{item_id:'{self.name}'}}]"

    __neg__ = __invert__ = conditional_string
    __pos__ = __str__ = item_string

    def __repr__(self):
        fields = ", ".join(
            f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("_")
        )
        return f"{self.name}[{fields}]"

    def __call__(self, /, **kwargs) -> Union["ItemMeta", tuple["ItemMeta", int]]:
        """Returns an anonymous item that inherits from this item with changes from kwargs"""

        if not kwargs:
            raise ItemError(f"Cannot instantiate `{self.name}` without changes!")
        
        # generate unique name
        name = self.ctx.generate.path(self.name + "_generated_{incr}").replace(":", "_").replace("/", "_")
        
        # get count before creating item
        count = None if "count" not in kwargs else kwargs.pop("count")

        new_cls = type(name, (self,), kwargs)

        if count:
            return new_cls, count

        return new_cls
