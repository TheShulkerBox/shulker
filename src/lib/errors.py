from typing import Any, Union


class ItemError(Exception):
    """Exceptions related to custom items"""


class ValidationError(ItemError):
    """Validation error for components and subcomponents / fields"""

    name: str
    value: Any
    expected: type
    suberrors: list[Union["ValidationError", Exception]]
    msg: str

    def __init__(
        self,
        name: str,
        value: Any,
        expected: str,
        suberrors: list[Union["ValidationError", Exception]] = [],
        msg: str = "",
    ):
        self.name = name
        self.value = value
        self.expected = expected
        self.suberrors = suberrors
        self.msg = msg
        super().__init__(msg)


class MissingValidationError(ValidationError): ...


class UnexpectedValidationError(ValidationError):
    def __init__(self, name: str, value: Any):
        super().__init__(name, value, "null", [])


class ComponentError(ItemError):
    """A component error"""

    name: str
    component: Any
    suberrors: list[ValidationError | Exception]
    msg: str

    def __init__(
        self,
        name: str,
        component: Any,
        suberrors: list[ValidationError] = [],
        msg: str = "",
    ):
        self.name = name
        self.component = component
        self.suberrors = suberrors
        self.msg = msg
        super().__init__(msg)

    def __str__(self):
        return str(
            [getattr(self, elem) for elem in dir(self) if not elem.startswith("_")]
        )


class NonExistentComponentError(ComponentError):
    """When an component does not exist"""

    def __init__(self, name: str):
        super().__init__(name, None, [])


class CustomComponentError(ComponentError):
    """Errors related to custom components"""

    def __init__(self, msg: str, name: str, component: Any):
        super().__init__(name, component, msg=msg)


class CustomTransformerError(ComponentError):
    """Errors related to custom transformers"""

    def __init__(self, msg: str, name: str, component: Any):
        super().__init__(name, component, msg=msg)
