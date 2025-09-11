from pydantic import BaseModel, Field, RootModel, model_validator
from beet import Context, JsonFile
from typing import Any, Iterable, Literal, Self, Union

MCDOC_URL = "https://api.spyglassmc.com/vanilla-mcdoc/symbols"
MCMETA_URL = "https://raw.githubusercontent.com/misode/mcmeta/refs/heads/summary/item_components/data.json"

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None

# Define the VERSION constant
VERSION = "1.21.8"


def compare_versions(v1: str, v2: str) -> int:
    _, *v1 = (int(part) for part in v1.split("."))
    _, *v2 = (int(part) for part in v2.split("."))

    if len(v1) < 2:
        v1.append(0)

    if len(v2) < 2:
        v2.append(0)

    if tuple(v1) > tuple(v2):
        return 1

    if tuple(v2) > tuple(v1):
        return -1

    return 0


def is_valid_with_attributes(
    attributes: list["Attribute"] | None, current_version: str = VERSION
) -> bool:
    """
    Checks if an object is valid based on its 'since' and 'until' attributes
    compared to the current_version.
    """

    if not attributes:
        return True

    for attr in attributes:
        if attr.name == "until":
            if isinstance(attr.value, LiteralSchema) and isinstance(
                attr.value.value, StringLiteralValue
            ):
                until_version = attr.value.value.value
                # If current_version is greater than or equal to until_version, it's no longer valid.
                if compare_versions(current_version, until_version) >= 0:
                    return False
        elif attr.name == "since":
            if isinstance(attr.value, LiteralSchema) and isinstance(
                attr.value.value, StringLiteralValue
            ):
                since_version = attr.value.value.value
                # If current_version is less than since_version, it's not yet valid.
                if compare_versions(current_version, since_version) < 0:
                    return False

    return True


class BaseSchema(BaseModel):
    """A base model to allow for recursive type definitions."""


class StringLiteralValue(BaseModel):
    kind: Literal["string"]
    value: str


class IntLiteralValue(BaseModel):
    kind: Literal["int"]
    value: int


class BooleanLiteralValue(BaseModel):
    kind: Literal["boolean"]
    value: bool


class ByteLiteralValue(BaseModel):
    kind: Literal["byte"]
    value: bool


LiteralValue = StringLiteralValue | IntLiteralValue | BooleanLiteralValue


class LiteralSchema(BaseModel):
    """Represents a literal value, often found inside an Attribute's value."""

    kind: Literal["literal"]
    value: LiteralValue


class TreeValue(RootModel[dict[str, Union[LiteralSchema, "ReferenceSchema"]]]):
    """Represents the 'values' part of a TreeSchema. It's a flexible dictionary."""

    root: dict[str, Union[LiteralSchema, "ReferenceSchema"]]


class TreeSchema(BaseSchema):
    """Represents a 'tree' structure, found inside an Attribute's value."""

    kind: Literal["tree"]
    values: TreeValue


class Attribute(BaseModel):
    """Represents a single attribute with a name and a structured value."""

    name: str
    value: Union[
        LiteralSchema, "ReferenceSchema", TreeSchema, "DispatcherSchema", None
    ] = None


class ValueRange(BaseModel):
    """Represents a numeric range, used in `int` and `float` kinds."""

    kind: int
    min: int | None = None
    max: int | None = None


class ReferenceSchema(BaseSchema):
    kind: Literal["reference"]
    path: str  # we look this up in the main mcdoc document
    attributes: list[Attribute] | None = None


class UnionSchema(BaseSchema):
    kind: Literal["union"]
    members: list["Schema"]
    attributes: list[Attribute] | None = None


class ListSchema(BaseSchema):
    kind: Literal["list"]
    item: "Schema"
    length_range: ValueRange | None = Field(None, alias="lengthRange")
    attributes: list[Attribute] | None = None


class IntArraySchema(BaseSchema):
    kind: Literal["int_array"]
    length_range: ValueRange | None = Field(None, alias="valueRange")
    attributes: list[Attribute] | None = None


class FloatArraySchema(BaseSchema):
    kind: Literal["float_array"] | Literal["double_array"]
    length_range: ValueRange | None = Field(None, alias="valueRange")
    attributes: list[Attribute] | None = None


class StringSchema(BaseSchema):
    kind: Literal["string"]
    attributes: list[Attribute] | None = None


class IntSchema(BaseSchema):
    kind: Literal["int"]
    value_range: ValueRange | None = Field(None, alias="valueRange")
    attributes: list[Attribute] | None = None


class FloatSchema(BaseSchema):
    kind: Literal["float"] | Literal["double"]
    value_range: ValueRange | None = Field(None, alias="valueRange")
    attributes: list[Attribute] | None = None


class BooleanSchema(BaseSchema):
    kind: Literal["boolean"]
    attributes: list[Attribute] | None = None


class ByteSchema(BaseSchema):
    kind: Literal["byte"]
    attributes: list[Attribute] | None = None


class PairField(BaseModel):
    kind: Literal["pair"]
    key: Union[str, "Schema"]
    type: "Schema"
    optional: bool = False
    desc: str | None = None
    attributes: list[Attribute] | None = None


class SpreadField(BaseModel):
    kind: Literal["spread"]
    type: "Schema"


class StructSchema(BaseSchema):
    kind: Literal["struct"]
    fields: list[PairField | SpreadField]
    attributes: list[Attribute] | None = None

    @model_validator(mode="after")
    def prune_on_version(self) -> Self:
        fields = []
        for field in self.fields:
            match field:
                case PairField(attributes=attributes):
                    if is_valid_with_attributes(attributes):
                        fields.append(field)
                case _:
                    fields.append(field)

        self.fields = fields
        return self


class EnumValue(BaseModel):
    desc: str | None = None
    identifier: str
    value: str


class EnumSchema(BaseSchema):
    kind: Literal["enum"]
    enum_kind: (
        Literal["byte"]
        | Literal["short"]
        | Literal["int"]
        | Literal["long"]
        | Literal["string"]
        | Literal["float"]
        | Literal["double"]
    ) = Field(..., alias="enumKind")
    values: list[EnumValue]
    attributes: list[Attribute] | None = None


class DynamicIndex(BaseModel):
    kind: Literal["dynamic"]
    accessor: list[Json]


class StaticIndex(BaseModel):
    kind: Literal["static"]
    value: str


class DispatcherSchema(BaseSchema):
    kind: Literal["dispatcher"]
    parallel_indices: list[DynamicIndex] = Field(..., alias="parallelIndices")
    registry: str
    attributes: list[Attribute] | None = None


class Schema(RootModel):
    root: (
        ReferenceSchema
        | UnionSchema
        | ListSchema
        | IntArraySchema
        | FloatArraySchema
        | StringSchema
        | IntSchema
        | FloatSchema
        | BooleanSchema
        | ByteSchema
        | StructSchema
        | EnumSchema
        | DispatcherSchema
        | None
    ) = Field(discriminator="kind")

    @model_validator(mode="after")
    def prune_on_version(self) -> Self:
        if self.root is not None and is_valid_with_attributes(self.root.attributes):
            return self

        self.root = None
        return self


Schema.model_rebuild()


def create_schemas(data: dict[str, Any]) -> Iterable[tuple[str, Schema]]:
    for key, val in data.items():
        yield key, Schema.model_validate(val)


def beet_default(ctx: Context):
    mcdoc_path = ctx.cache["mcdoc"].download(MCDOC_URL)
    mcmeta_path = ctx.cache["mcmeta_item_components"].download(MCMETA_URL)
    mcdoc_file = JsonFile(source_path=mcdoc_path)
    mcmeta_file = JsonFile(source_path=mcmeta_path)

    ctx.meta["mcdoc"] = mcdoc_file.data
    ctx.meta["item_component_schemas"] = dict(
        create_schemas(mcdoc_file.data["mcdoc/dispatcher"]["minecraft:data_component"])
    )
    ctx.meta["item_component_defaults"] = mcmeta_file.data
