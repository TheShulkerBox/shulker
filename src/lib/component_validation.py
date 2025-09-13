import json
from typing import Any
import logging

from plugins.component_caching import (
    ByteSchema,
    Schema,
    Json,
    ReferenceSchema,
    UnionSchema,
    ListSchema,
    IntArraySchema,
    FloatArraySchema,
    StringSchema,
    IntSchema,
    FloatSchema,
    BooleanSchema,
    PairField,
    SpreadField,
    StructSchema,
    EnumSchema,
    DispatcherSchema,
)
from lib.errors import (
    MissingValidationError,
    UnexpectedValidationError,
    ValidationError,
)

logger = logging.getLogger(__name__)


SchemaFile = dict[str, Schema]


def resolve_schema_reference(path: str, mcdoc: dict[str, Any]) -> Schema:
    """
    Resolves a schema reference path within the mcdoc document.
    Assumes mcdoc contains either raw dict representations of schemas or parsed Schema objects.
    """

    try:
        return Schema.model_validate(mcdoc[path])
    except Exception as err:
        # TODO: clean up
        logger.debug(json.dumps(mcdoc[path]))
        logger.debug(err)

    return Schema.model_construct(None)  # dummy schema, no validation


def validate_data(
    data: Json,
    schema: Schema,
    mcdoc: dict[str, Any],
    path: list[str | int],
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
                raise MissingValidationError(path[-1], None, "union")

        case ListSchema(item=item_schema, length_range=length_range):
            if not isinstance(data, list):
                raise ValidationError(path[-1], data, "list")

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list",
                        msg=f"List length {length} is less than minimum required {length_range.min}",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list",
                        msg=f"List length {length} is greater than maximum allowed {length_range.min}",
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
                raise ValidationError(path[-1], data, "list")

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list[int]",
                        msg=f"List length {length} is less than minimum required {length_range.min}",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list[int]",
                        msg=f"List length {length} is greater than maximum allowed {length_range.min}",
                    )

            item_errors = []
            for i, item in enumerate(data):
                try:
                    if isinstance(item) is not int:
                        raise ValidationError(i, data, "int")
                except (ValidationError, ExceptionGroup) as e:
                    item_errors.append(e)
            if item_errors:
                raise ExceptionGroup(
                    "Multiple items in list failed validation", item_errors
                )

        case FloatArraySchema(length_range=length_range):
            if not isinstance(data, list):
                raise ValidationError(path[-1], data, "list")

            if length_range is not None:
                length = len(data)
                if length_range.min is not None and length < length_range.min:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list[float]",
                        msg=f"List length {length} is less than minimum required {length_range.min}",
                    )
                if length_range.max is not None and length > length_range.max:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list[float]",
                        msg=f"List length {length} is greater than maximum allowed {length_range.min}",
                    )

            item_errors = []
            for i, item in enumerate(data):
                try:
                    if isinstance(item) is not float:
                        raise ValidationError(i, data, "float")
                except (ValidationError, ExceptionGroup) as e:
                    item_errors.append(e)
            if item_errors:
                raise ExceptionGroup(
                    "Multiple items in list failed validation", item_errors
                )

        case StringSchema():
            if not isinstance(data, str):
                raise ValidationError(path[-1], data, "str")

        case IntSchema(value_range=value_range):
            if not isinstance(data, int):
                raise ValidationError(path[-1], data, "int")

            if value_range:
                if value_range.min is not None and data < value_range.min:
                    raise ValidationError(
                        path[-1],
                        data,
                        "int",
                        msg=f"Int {data} is less than minimum allowed {value_range.min}",
                    )
                if value_range.max is not None and data > value_range.max:
                    raise ValidationError(
                        path[-1],
                        data,
                        "int",
                        msg=f"Int {data} is greater than maxinum allowed {value_range.max}",
                    )

        case FloatSchema(value_range=value_range):
            # Allow integers for float schema as they can be represented as floats
            if not isinstance(data, (int, float)):
                raise ValidationError(path[-1], data, "float")

            if value_range:
                if value_range.min is not None and data < value_range.min:
                    raise ValidationError(
                        path[-1],
                        data,
                        "float",
                        msg=f"Number {data} is less than minimum allowed {value_range.min}",
                    )
                if value_range.max is not None and data > value_range.max:
                    raise ValidationError(
                        path[-1],
                        data,
                        "float",
                        msg=f"Number {data} is greater than maxinum allowed {value_range.max}",
                    )

        case BooleanSchema():
            if not isinstance(data, bool):
                raise ValidationError(path[-1], data, "bool")

        case ByteSchema():
            if not isinstance(data, (int, bool)):
                raise ValidationError(path[-1], data, "byte")

        case StructSchema(fields=fields):
            if not isinstance(data, dict):
                raise ValidationError(path[-1], data, "dict")

            remaining_keys = set(data.keys())
            spread_schema: Schema | None = None
            has_spread_field = False
            struct_errors = []

            for field in fields:
                match field:
                    case PairField(key=field_key, type=field_type, optional=optional):
                        if isinstance(field_key, Schema):
                            # TODO WEE WOO
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
                                MissingValidationError(field_key, data, "dict")
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
                        struct_errors.append(UnexpectedValidationError(key, data))

            if struct_errors:
                raise ExceptionGroup(
                    "Multiple errors in struct validation", struct_errors
                )

        case EnumSchema(enum_kind=enum_kind, values=values):
            match enum_kind:
                case "string":
                    if not isinstance(data, str):
                        raise ValidationError(path[-1], data, "str")

                case "int" | "short" | "long" as typ:
                    if not isinstance(data, int):
                        raise ValidationError(path[-1], data, typ)
                case "bytes":
                    if not isinstance(data, (bool, int)):
                        raise ValidationError(path[-1], data, "bytes")
                case "float" | "double" as typ:
                    if not isinstance(data, (int, float)):
                        raise ValidationError(path[-1], data, typ)

            if data not in (enum_identifiers := {value.value for value in values}):
                raise ValidationError(path[-1], data, f"enum {enum_identifiers}")

        case DispatcherSchema(
            parallel_indices=parallel_indices, registry=registry_path
        ):
            if not isinstance(data, dict):
                raise ValidationError(path[-1], data, "dictionary (dispatcher)")

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
                                path[-1],
                                data,
                                "dispatcher",
                                msg=f"Could not access part '{accessor_part}' in data for dispatcher key extraction",
                            )
                    extracted_key_parts.append(str(current_val_for_accessor))
                except ValidationError as e:
                    dispatcher_accessor_errors.append(e)
                except Exception as e:
                    # Catch any other unexpected errors during accessor traversal
                    dispatcher_accessor_errors.append(
                        ValidationError(
                            path[-1],
                            data,
                            "dispatcher",
                            suberrors=[e],
                            msg="Unexpected error during dispatcher key extraction",
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
                        path[-1],
                        data,
                        "dispatcher",
                        msg="No dispatcher key could be extracted from parallel indices.",
                    )

            # For simplicity, we use the first successfully extracted key if multiple are found.
            lookup_key = extracted_key_parts[0]

            resolved_registry_schema_wrapper = resolve_schema_reference(
                registry_path, mcdoc
            )

            if not (isinstance(resolved_registry_schema_wrapper.root, dict)):
                raise ValidationError(
                    path[-1],
                    data,
                    "dispatcher",
                    msg=f"Registry '{registry_path}' must resolve to a Schema whose root is a dictionary of schemas, got {type(resolved_registry_schema_wrapper.root).__name__}.",
                )

            registry_map_raw = resolved_registry_schema_wrapper.root

            if lookup_key not in registry_map_raw:
                raise ValidationError(
                    path[-1],
                    data,
                    "dispatcher",
                    msg=f"Dispatcher key '{lookup_key}' not found in registry '{registry_path}'.",
                )

            target_schema_raw = registry_map_raw[lookup_key]
            try:
                target_schema = Schema.model_validate(target_schema_raw)
            except Exception as e:
                raise ValidationError(
                    path[-1],
                    data,
                    "dispatcher",
                    suberrors=[e],
                    msg=f"Failed to parse schema for key '{lookup_key}' in registry '{registry_path}'",
                )

            # Validate the entire data against the resolved target schema
            validate_data(data, target_schema, mcdoc, path)
