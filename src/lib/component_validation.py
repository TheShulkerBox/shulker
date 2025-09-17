from dataclasses import dataclass
from methodtools import lru_cache
import json
from typing import Any, ClassVar
import logging

from beet import Context

from plugins.component_caching import (
    BooleanLiteralValue,
    ByteLiteralValue,
    ByteSchema,
    DynamicIndex,
    IntLiteralValue,
    LiteralSchema,
    Schema,
    Json,
    ReferenceSchema,
    StaticIndex,
    StringLiteralValue,
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


cache = lru_cache(maxsize=None)


@dataclass
class McdocValidator:
    ctx: Context

    mcdoc: ClassVar[dict[str, Any]]

    def __post_init__(self):
        self.mcdoc = self.ctx.meta["mcdoc"]

    @cache
    def get_mcdoc_schema(self, path: str) -> Schema:
        """
        Resolves a schema reference path within the mcdoc document.
        Assumes mcdoc contains either raw dict representations of schemas or parsed Schema objects.
        """

        try:
            return Schema.model_validate(data := self.mcdoc["mcdoc"][path])
        except Exception as err:
            # TODO: clean up
            logger.debug(json.dumps(data))
            logger.debug(err)

        return Schema.model_construct(None)  # dummy schema, no validation

    @cache
    def get_dispatcher_schema(self, path: str) -> dict[str, Schema]:
        """
        Resolves a schema reference path within the mcdoc document.
        Assumes mcdoc contains either raw dict representations of schemas or parsed Schema objects.
        """

        try:
            data = self.mcdoc["mcdoc/dispatcher"][path]
            return {key: Schema.model_validate(value) for key, value in data.items()}

        except Exception as err:
            # TODO: clean up
            logger.debug(json.dumps(data))
            logger.debug(err)

        return Schema.model_construct(None)  # dummy schema, no validation

    def validate_data(
        self,
        data: Json,
        schema: Schema,
        path: list[str | int],
        parent: Json | None = None
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
                resolved_schema = self.get_mcdoc_schema(ref_path)
                self.validate_data(data, resolved_schema, path)

            case UnionSchema(members=members):
                errors = []
                for i, member_schema in enumerate(members):
                    try:
                        self.validate_data(data, member_schema, path)
                        if member_schema.root is not None:
                            return  # If any member validates, the union is valid
                    except (ValidationError, ExceptionGroup) as e:
                        errors.append(e)
                if errors:
                    raise ValidationError(
                        path[1],
                        data,
                        "union",
                        errors,
                        f"Data failed to validate against any of the {len(members)} union members",
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
                        self.validate_data(item, item_schema, path + [i], data)
                    except (ValidationError, ExceptionGroup) as e:
                        item_errors.append(e)
                if item_errors:
                    raise ValidationError(
                        path[-1],
                        data,
                        "list",
                        item_errors,
                        "Multiple items in list failed validation",
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
                    raise ValidationError(
                        path[-1],
                        data,
                        "array[int]",
                        item_errors,
                        "Multiple items in list failed validation",
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
                    raise ValidationError(
                        path[-1],
                        data,
                        "list[float]",
                        item_errors,
                        "Multiple items in list failed validation",
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

            case LiteralSchema(value=literal):
                match literal:
                    case IntLiteralValue(value=value):
                        ...
                    case BooleanLiteralValue(value=value):
                        ...
                    case StringLiteralValue(value=value):
                        ...
                    case ByteLiteralValue(value=value):
                        ...

                if data != value:
                    raise ValidationError(path[-1], data, value)

            case StructSchema(fields=fields):
                if not isinstance(data, dict):
                    raise ValidationError(path[-1], data, "dict")

                remaining_keys = set(data.keys())
                spread_schema: Schema | None = None
                has_spread_field = False
                struct_errors = []

                for field in fields:
                    match field:
                        case PairField(
                            key=field_key, type=field_type, optional=optional
                        ):
                            if isinstance(field_key, Schema):
                                # TODO WEE WOO
                                print(
                                    f"Warning. Unsure what to do /shrug. {field_key}\n{data}"
                                )
                                continue

                            if field_key in data:
                                try:
                                    remaining_keys.discard(field_key)
                                    self.validate_data(
                                        data[field_key],
                                        field_type,
                                        path + [field_key],
                                        data,
                                    )
                                except (ValidationError, ExceptionGroup) as e:
                                    struct_errors.append(e)
                            elif not optional:
                                struct_errors.append(
                                    MissingValidationError(field_key, field, "dict")
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
                        try:
                            self.validate_data({key: data[key] for key in remaining_keys}, spread_schema, path, data)
                        except (ValidationError, ExceptionGroup) as e:
                            struct_errors.append(e)
                    else:
                        for key in remaining_keys:
                            struct_errors.append(
                                UnexpectedValidationError(key, data[key])
                            )

                if struct_errors:
                    raise ValidationError(
                        path[-1],
                        data,
                        "dict",
                        struct_errors,
                        "Multiple errors in struct validation",
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
                if not isinstance(data, (list, dict)):
                    raise ValidationError(path[-1], data, "dispatcher (list|dict)")

                if (registry := self.get_dispatcher_schema(registry_path)) is None:
                    raise ValidationError(registry_path, None, "registry not found")

                union_types = []
                for index in parallel_indices:
                    match index:
                        case DynamicIndex(accessor=accessors):
                            union_types.extend(
                                (parent[accessor], accessor)
                                for accessor in accessors
                                if type(accessor) is str
                            )
                        case StaticIndex(value=value):
                            union_types.append((value, None))

                fallback = False
                for typ, accessor in union_types:
                    if found_schema := registry.get(typ):
                        self.validate_data(
                            {k: v for k, v in data.items() if k != accessor},
                            found_schema,
                            path,
                            data,
                        )
                        break

                    if typ.startswith("%"):
                        fallback = True
                else:
                    if not fallback:
                        raise ValidationError("dispatcher not found")
