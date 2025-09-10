import json
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
    

def is_valid_with_attributes(attributes: list["Attribute"] | None, current_version: str = VERSION) -> bool:
    """
    Checks if an object is valid based on its 'since' and 'until' attributes
    compared to the current_version.
    """

    if not attributes:
        return True

    for attr in attributes:
        if attr.name == "until":
            if isinstance(attr.value, LiteralSchema) and isinstance(attr.value.value, StringLiteralValue):
                until_version = attr.value.value.value
                # If current_version is greater than or equal to until_version, it's no longer valid.
                if compare_versions(current_version, until_version) >= 0:
                    return False
        elif attr.name == "since":
            if isinstance(attr.value, LiteralSchema) and isinstance(attr.value.value, StringLiteralValue):
                since_version = attr.value.value.value
                # If current_version is less than since_version, it's not yet valid.
                if compare_versions(current_version, since_version) < 0:
                    return False
    
    return True


class ValidationError(Exception):
    """
    Custom exception for schema validation errors, including path and schema kind.
    """

    def __init__(
        self, message: str, path: list[str | int] | None = None, schema_kind: str = None
    ):
        super().__init__(message)
        self.path = path if path is not None else []
        self.schema_kind = schema_kind

    def __str__(self):
        path_str = ".".join(map(str, self.path))
        if path_str:
            s = f"Validation Error at '{path_str}'"
        else:
            s = "Validation Error"
        
        if self.schema_kind:
            s = f"{s} (Schema: {self.schema_kind})"
        
        return f"{s}: {super().__str__()}"


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
    value: Union[LiteralSchema, "ReferenceSchema", TreeSchema, "DispatcherSchema", None] = None


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

    @model_validator(mode='after')
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
        | StructSchema
        | EnumSchema
        | DispatcherSchema
        | None
    ) = Field(discriminator="kind")

    @model_validator(mode='after')
    def prune_on_version(self) -> Self:
        if self.root is not None and is_valid_with_attributes(self.root.attributes):
            return self

        self.root = None
        return self


Schema.model_rebuild()
SchemaFile = dict[str, Schema]


def create_schemas(data: dict[str, Any]) -> Iterable[tuple[str, Schema]]:
    for key, val in data.items():
        yield key, Schema.model_validate(val)


def resolve_schema_reference(path: str, mcdoc: dict[str, Any]) -> Schema:
    """
    Resolves a schema reference path within the mcdoc document.
    Assumes mcdoc contains either raw dict representations of schemas or parsed Schema objects.
    """

    try:
        return Schema.model_validate(mcdoc[path])
    except Exception as err:
        print(json.dumps(mcdoc[path]))
        print(err)
    
    return Schema.model_construct(None)  # dummy schema, no validation


def validate_data(
    data: Json,
    schema: Schema,
    mcdoc: dict[str, Any],
    path: list[str | int] | None = None,
):
    """
    Validates a given JSON-like data structure against a specified schema,
    raising exceptions on failure.

    Args:
        data: The JSON-like data to validate.
        schema: The schema definition to validate against. This is expected to be
                an instance of the Schema (RootModel) class.
        mcdoc: A dictionary containing referenced schema definitions.
               These definitions can be raw dictionaries or already parsed Schema objects.
        path: Internal list to track the current data path for error reporting.

    Raises:
        ValidationError: If the data does not conform to the schema.
        ExceptionGroup: If multiple validation errors occur (e.g., in UnionSchema or ListSchema).
        ValueError: For issues within the schema definition itself (e.g., multiple SpreadFields).
    """

    path = path if path is not None else []

    match schema.root:
        case ReferenceSchema(path=ref_path):
            resolved_schema = resolve_schema_reference(ref_path, mcdoc)
            validate_data(data, resolved_schema, mcdoc, path)

        case UnionSchema(members=members):
            errors = []
            for i, member_schema in enumerate(members):
                try:
                    validate_data(data, member_schema, mcdoc, path)
                    return  # If any member validates, the union is valid
                except (ValidationError, ExceptionGroup) as e:
                    errors.append(e)
            if errors:
                raise ExceptionGroup(
                    f"Data failed to validate against any of the {len(members)} union members",
                    errors,
                )
            else:
                # This case should ideally not be hit if members list is not empty
                raise ValidationError(
                    "UnionSchema has no members to validate against.", path, "union"
                )

        case ListSchema(item=item_schema, length_range=length_range):
            if not isinstance(data, list):
                raise ValidationError(
                    f"Expected a list, got {type(data).__name__}", path, "list"
                )

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        f"List length {length} is less than minimum required {length_range.min}",
                        path,
                        "list",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        f"List length {length} is greater than maximum allowed {length_range.max}",
                        path,
                        "list",
                    )

            item_errors = []
            for i, item in enumerate(data):
                try:
                    validate_data(item, item_schema, mcdoc, path + [i])
                except (ValidationError, ExceptionGroup) as e:
                    item_errors.append(e)
            if item_errors:
                raise ExceptionGroup(
                    "Multiple items in list failed validation", item_errors
                )

        case IntArraySchema(length_range=length_range):
            if not isinstance(data, list):
                raise ValidationError(
                    f"Expected a list, got {type(data).__name__}", path, "list"
                )

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        f"List length {length} is less than minimum required {length_range.min}",
                        path,
                        "list",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        f"List length {length} is greater than maximum allowed {length_range.max}",
                        path,
                        "list",
                    )

            item_errors = []
            for i, item in enumerate(data):
                try:
                    if isinstance(item) is not int:
                        raise ValidationError(
                            f"Expected an integer, got {type(item).__name__}",
                            path + [i],
                            "int",
                        )
                except (ValidationError, ExceptionGroup) as e:
                    item_errors.append(e)
            if item_errors:
                raise ExceptionGroup(
                    "Multiple items in list failed validation", item_errors
                )

        case FloatArraySchema(length_range=length_range):
            if not isinstance(data, list):
                raise ValidationError(
                    f"Expected a list, got {type(data).__name__}", path, "list"
                )

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        f"List length {length} is less than minimum required {length_range.min}",
                        path,
                        "list",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        f"List length {length} is greater than maximum allowed {length_range.max}",
                        path,
                        "list",
                    )

            item_errors = []
            for i, item in enumerate(data):
                try:
                    if isinstance(item) is not float:
                        raise ValidationError(
                            f"Expected an integer, got {type(item).__name__}",
                            path + [i],
                            "float",
                        )
                except (ValidationError, ExceptionGroup) as e:
                    item_errors.append(e)
            if item_errors:
                raise ExceptionGroup(
                    "Multiple items in list failed validation", item_errors
                )

        case StringSchema():
            if not isinstance(data, str):
                raise ValidationError(
                    f"Expected a string, got {type(data).__name__}", path, "string"
                )

        case IntSchema(value_range=value_range):
            if not isinstance(data, int):
                raise ValidationError(
                    f"Expected an integer, got {type(data).__name__}", path, "int"
                )
            if value_range:
                if value_range.min is not None and data < value_range.min:
                    raise ValidationError(
                        f"Integer value {data} is less than minimum allowed {value_range.min}",
                        path,
                        "int",
                    )
                if value_range.max is not None and data > value_range.max:
                    raise ValidationError(
                        f"Integer value {data} is greater than maximum allowed {value_range.max}",
                        path,
                        "int",
                    )

        case FloatSchema(value_range=value_range):
            # Allow integers for float schema as they can be represented as floats
            if not isinstance(data, (int, float)):
                raise ValidationError(
                    f"Expected a number (int or float), got {type(data).__name__}",
                    path,
                    "float",
                )
            if value_range:
                if value_range.min is not None and data < value_range.min:
                    raise ValidationError(
                        f"Number value {data} is less than minimum allowed {value_range.min}",
                        path,
                        "float",
                    )
                if value_range.max is not None and data > value_range.max:
                    raise ValidationError(
                        f"Number value {data} is greater than maximum allowed {value_range.max}",
                        path,
                        "float",
                    )

        case BooleanSchema():
            if not isinstance(data, bool):
                raise ValidationError(
                    f"Expected a boolean, got {type(data).__name__}", path, "boolean"
                )

        case StructSchema(fields=fields):
            if not isinstance(data, dict):
                raise ValidationError(
                    f"Expected a dictionary, got {type(data).__name__}", path, "struct"
                )

            remaining_keys = set(data.keys())
            spread_schema: Schema | None = None
            has_spread_field = False
            struct_errors = []

            for field in fields:
                match field:
                    case PairField(key=field_key, type=field_type, optional=optional):
                        if isinstance(field_key, Schema):
                            print(
                                f"Warning. Unsure what to do /shrug. {field_key}\n{data}"
                            )
                            continue

                        if field_key in data:
                            try:
                                validate_data(
                                    data[field_key],
                                    field_type,
                                    mcdoc,
                                    path + [field_key],
                                )
                                remaining_keys.discard(field_key)
                            except (ValidationError, ExceptionGroup) as e:
                                struct_errors.append(e)
                        elif not optional:
                            struct_errors.append(
                                ValidationError(
                                    f"Missing required field '{field_key}'",
                                    path + [field_key],
                                    "struct",
                                )
                            )
                    case SpreadField(type=spread_type):
                        if has_spread_field:
                            # This is a schema definition error, not a data validation error.
                            raise ValueError(
                                f"StructSchema at '{'.'.join(map(str, path))}' contains multiple SpreadFields, which is ambiguous."
                            )
                        spread_schema = spread_type
                        has_spread_field = True

            if remaining_keys:
                if spread_schema:
                    for key in remaining_keys:
                        try:
                            validate_data(data[key], spread_schema, mcdoc, path + [key])
                        except (ValidationError, ExceptionGroup) as e:
                            struct_errors.append(e)
                else:
                    for key in remaining_keys:
                        struct_errors.append(
                            ValidationError(
                                f"Unexpected field '{key}'", path + [key], "struct"
                            )
                        )

            if struct_errors:
                raise ExceptionGroup(
                    "Multiple errors in struct validation", struct_errors
                )

        case EnumSchema(enum_kind=enum_kind, values=values):
            match enum_kind:
                case "string":
                    if not isinstance(data, str):
                        raise ValidationError(
                            f"Expected a string, got {type(data).__name__}",
                            path,
                            "string",
                        )

                case "int" | "short" | "long" as typ:
                    if not isinstance(data, int):
                        raise ValidationError(
                            f"Expected an {typ}, got {type(data).__name__}", path, typ
                        )
                case "bytes":
                    if not isinstance(data, (bool, int)):
                        raise ValidationError(
                            f"Expected bytes, got {type(data).__name__}", path, "bytes"
                        )
                case "float" | "double" as typ:
                    if not isinstance(data, (int, float)):
                        raise ValidationError(
                            f"Expected {typ}, got {type(data).__name__}", path, typ
                        )

            if data not in (enum_identifiers := {value.value for value in values}):
                raise ValidationError(
                    f"Expected one of {enum_identifiers}, got {data}", path, "enum"
                )

        case DispatcherSchema(
            parallel_indices=parallel_indices, registry=registry_path
        ):
            if not isinstance(data, dict):
                raise ValidationError(
                    f"Expected a dictionary for dispatcher, got {type(data).__name__}",
                    path,
                    "dispatcher",
                )

            extracted_key_parts = []
            dispatcher_accessor_errors = []
            for i, dynamic_index in enumerate(parallel_indices):
                current_val_for_accessor = data
                try:
                    for j, accessor_part in enumerate(dynamic_index.accessor):
                        if (
                            isinstance(current_val_for_accessor, dict)
                            and accessor_part in current_val_for_accessor
                        ):
                            current_val_for_accessor = current_val_for_accessor[
                                accessor_part
                            ]
                        elif (
                            isinstance(current_val_for_accessor, list)
                            and isinstance(accessor_part, int)
                            and 0 <= accessor_part < len(current_val_for_accessor)
                        ):
                            current_val_for_accessor = current_val_for_accessor[
                                accessor_part
                            ]
                        else:
                            raise ValidationError(
                                f"Could not access part '{accessor_part}' in data for dispatcher key extraction",
                                path + [f"parallelIndices[{i}].accessor[{j}]"],
                                "dispatcher",
                            )
                    extracted_key_parts.append(str(current_val_for_accessor))
                except ValidationError as e:
                    dispatcher_accessor_errors.append(e)
                except Exception as e:
                    # Catch any other unexpected errors during accessor traversal
                    dispatcher_accessor_errors.append(
                        ValidationError(
                            f"Unexpected error during dispatcher key extraction: {e}",
                            path + [f"parallelIndices[{i}]"],
                            "dispatcher",
                        )
                    )

            if not extracted_key_parts:
                if dispatcher_accessor_errors:
                    raise ExceptionGroup(
                        "Failed to extract a dispatcher key from any parallel index",
                        dispatcher_accessor_errors,
                    )
                else:
                    raise ValidationError(
                        "No dispatcher key could be extracted from parallel indices.",
                        path,
                        "dispatcher",
                    )

            # For simplicity, we use the first successfully extracted key if multiple are found.
            lookup_key = extracted_key_parts[0]

            resolved_registry_schema_wrapper = resolve_schema_reference(
                registry_path, mcdoc
            )

            if not (isinstance(resolved_registry_schema_wrapper.root, dict)):
                raise ValidationError(
                    f"Registry '{registry_path}' must resolve to a Schema whose root is a dictionary of schemas, got {type(resolved_registry_schema_wrapper.root).__name__}.",
                    path,
                    "dispatcher",
                )

            registry_map_raw = resolved_registry_schema_wrapper.root

            if lookup_key not in registry_map_raw:
                raise ValidationError(
                    f"Dispatcher key '{lookup_key}' not found in registry '{registry_path}'.",
                    path,
                    "dispatcher",
                )

            target_schema_raw = registry_map_raw[lookup_key]
            try:
                target_schema = Schema.model_validate(target_schema_raw)
            except Exception as e:
                raise ValidationError(
                    f"Failed to parse schema for key '{lookup_key}' in registry '{registry_path}': {e}",
                    path,
                    "dispatcher",
                )

            # Validate the entire data against the resolved target schema
            validate_data(data, target_schema, mcdoc, path)


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
