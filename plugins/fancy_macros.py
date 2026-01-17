from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Generator,
    List,
    Literal,
    Optional,
    TypeVar,
    cast,
)
from beet import Context
from beet.core.utils import required_field
from bolt import (
    Accumulator,
    AstFormatString,
    AstInterpolation,
    Runtime,
    visit_generic,
    visit_single,
)
from mecha import (
    NUMBER_PATTERN,
    AlternativeParser,
    AstChildren,
    AstCommand,
    AstGreedy,
    AstMacroLineVariable,
    AstMessage,
    AstNbtPath,
    AstNbtPathKey,
    AstNbtValue,
    AstNode,
    AstString,
    AstWord,
    CommandSpec,
    Mecha,
    MutatingReducer,
    NbtPathParser,
    Parser,
    Visitor,
    delegate,
    rule,
)
from mecha.utils import string_to_number, number_to_string
from nbtlib import Base, Serializer as NbtSerializer
from tokenstream import InvalidSyntax, TokenStream, set_location

import re

MACRO_REGEX = re.compile(r"\$\(\s*\w+\s*(\:\s*\w+\s*)?\)")

T = TypeVar("T")
N = TypeVar("N", bound=AstNode)


@dataclass
class MacroTag(Base):
    name: str = required_field()
    parser: str | None = required_field()

    def __post_init__(self):
        self.serializer = "macro"


def serialize_macro(_self: NbtSerializer, tag: MacroTag):
    if tag.parser == "string":
        return f'"$({tag.name})"'

    return f"$({tag.name})"


class MacroRepresentation: ...


@dataclass(frozen=True, slots=True)
class AstMacroArgument(AstNode, MacroRepresentation):
    name: str = required_field()
    parser: str | None = required_field()


@dataclass(frozen=True, slots=True)
class AstMacroNbtArgument(AstMacroArgument):
    def evaluate(self):
        return MacroTag(self.name, self.parser)


@dataclass(frozen=True, slots=True)
class AstMacroCoordinateArgument(AstMacroArgument):
    type: Literal["absolute", "local", "relative"] = required_field()


@dataclass(frozen=True, slots=True)
class AstMacroNbtPathKeyArgument(AstMacroArgument): ...


@dataclass(frozen=True, slots=True)
class AstMacroNbtPathArgument(AstMacroArgument): ...


@dataclass(frozen=True, slots=True)
class AstMacroExpression(AstMacroArgument): ...


@dataclass(frozen=True, slots=True)
class AstMacroRange(AstNode):
    min: int | float | AstMacroArgument | None = field(default=None)
    max: int | float | AstMacroArgument | None = field(default=None)


@dataclass(frozen=True, slots=True)
class AstMacroStringWrapper[N](AstNode):
    child: N = required_field()


@dataclass(frozen=True, slots=True)
class AstNbtValueWithMacro(AstNbtValue, MacroRepresentation):
    @classmethod
    def from_value(cls, value: Any) -> "AstNbtValueWithMacro":
        return cls(value=value)


@dataclass(frozen=True, slots=True)
class AstStringWithMacro(AstString, MacroRepresentation):
    @classmethod
    def from_value(cls, value: Any) -> "AstStringWithMacro":
        return AstStringWithMacro(value=str(value))


@dataclass(frozen=True, slots=True)
class AstGreedyWithMacro(AstGreedy, MacroRepresentation):
    @classmethod
    def from_value(cls, value: Any) -> "AstGreedyWithMacro":
        return cls(value=AstGreedy.from_value(value).value)


@dataclass(frozen=True, slots=True)
class AstWordWithMacro(AstWord, MacroRepresentation):
    @classmethod
    def from_value(cls, value: Any) -> "AstWordWithMacro":
        return cls(value=AstWord.from_value(value).value)


@dataclass(frozen=True, slots=True)
class AstMessageWithMacro(AstMessage, MacroRepresentation):
    @classmethod
    def from_value(cls, value: Any) -> "AstMessageWithMacro":
        return cls(fragments=AstMessage.from_value(value).fragments)


class StringWithMacro(str): ...


@dataclass
class Macro:
    name: str = required_field()
    parser: str | None = required_field()

    def __str__(self):
        return f"$({self.name})"


def ast_to_macro(macro: AstMacroArgument):
    return Macro(macro.name, macro.parser)


def make_macro_string():
    return StringWithMacro


@dataclass
class MacroCodegen(Visitor):
    @rule(AstMacroExpression)
    def macro(
        self, node: AstMacroExpression, acc: Accumulator
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        result = yield from visit_generic(node, acc)

        if result is None:
            result = acc.make_ref(node)

        result = acc.helper("ast_to_macro", result)

        return [result]

    @rule(AstMacroStringWrapper)
    def wrapper(
        self, node: AstMacroStringWrapper, acc: Accumulator
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        child = yield from visit_single(node.child, required=True)

        result = acc.make_variable()
        acc.statement(f"{result} = {acc.helper("make_macro_string")}({child})")

        return [result]


@dataclass
class MacroMutator(MutatingReducer):
    @rule(AstFormatString)
    def format_string(self, node: AstFormatString):
        if any(map(lambda v: isinstance(v, AstMacroArgument), node.values)):
            return set_location(
                AstMacroStringWrapper(child=node), node.location, node.end_location
            )

        return node


@dataclass
class CommandSerializer(Visitor):
    spec: CommandSpec = required_field()

    @rule(AstCommand)
    def command(self, node: AstCommand, result: list[str]):
        prototype = self.spec.prototypes[node.identifier]
        argument_index = 0

        sep = ""

        start_index = 0
        for i in range(len(result) - 1, -1, -1):
            if result[i] == "\n":
                start_index = i + 1
                break

        for token in prototype.signature:
            result.append(sep)
            sep = " "

            if isinstance(token, str):
                result.append(token)
            else:
                argument = node.arguments[argument_index]
              
                for child in argument.walk():
                    if isinstance(child, MacroRepresentation):
                        result[start_index] = "$"
                        break

                yield argument
                argument_index += 1

        if result[start_index] == "$":
            return

        for i in range(start_index, len(result)):
            if result[i] == "$(" and result[i + 2] == ")":
                result[start_index] = "$"
                break

    def default(self, argument: AstMacroArgument, result: list[str]):
        string = argument.parser == "string"
        if string:
            result.append('"')

        result.append("$(")
        result.append(argument.name)
        result.append(")")

        if string:
            result.append('"')

    @rule(AstMacroArgument, AstMacroNbtPathArgument, AstMacroNbtArgument)
    def macro(self, argument: AstMacroArgument, result: list[str]):
        self.default(argument, result)

    @rule(AstMacroCoordinateArgument)
    def coordinate(self, argument: AstMacroCoordinateArgument, result: list[str]):
        if argument.type == "local":
            result.append("^")
        elif argument.type == "relative":
            result.append("~")

        self.default(argument, result)

    @rule(AstMacroNbtPathKeyArgument)
    def macro_path_key(self, argument: AstMacroNbtPathKeyArgument, result: list[str]):
        self.default(argument, result)

    @rule(AstNbtPath)
    def nbt_path(self, node: AstNbtPath, result: List[str]):
        sep = ""
        for component in node.components:
            if isinstance(
                component,
                (AstNbtPathKey, AstMacroNbtPathKeyArgument, AstMacroNbtPathArgument),
            ):
                result.append(sep)
            sep = "."
            yield component

    @rule(AstMacroRange)
    def range(self, node: AstMacroRange, result: list[str]):
        if node.min == node.max and node.min is not None:
            if isinstance(node.min, AstMacroArgument):
                yield node.min
            else:
                result.append(number_to_string(node.min))
        else:
            if node.min is not None:
                if isinstance(node.min, AstMacroArgument):
                    yield node.min
                else:
                    result.append(number_to_string(node.min))

            result.append("..")

            if node.max is not None:
                if isinstance(node.max, AstMacroArgument):
                    yield node.max
                else:
                    result.append(number_to_string(node.max))


@dataclass
class MacroParser:
    parser: str | tuple[str, ...]
    node_type: type[AstMacroArgument]

    def __call__(self, stream: TokenStream):
        macro: AstMacroArgument = delegate("typed_macro", stream)

        if macro.parser:
            if isinstance(self.parser, str) and macro.parser != self.parser:
                raise ValueError(
                    f"Invalid macro type, received {macro.parser} expected {self.parser}"
                )
            elif macro.parser not in self.parser:
                raise ValueError(
                    f"Invalid macro type, received {macro.parser} expected one of {', '.join(self.parser)}"
                )

        parser = macro.parser

        if isinstance(self.parser, tuple) and parser is None:
            parser = self.parser[0]
        elif isinstance(self.parser, str):
            parser = self.parser

        if not isinstance(macro, self.node_type):
            return self.node_type(name=macro.name, parser=parser)

        return macro


def macro(
    parsers: dict[str, Parser],
    type: str | tuple[str],
    priority=False,
    node_type: type[AstMacroArgument] = AstMacroArgument,
):
    parser_type = type
    if isinstance(type, tuple):
        parser_type = type[0]

    if not priority:
        return AlternativeParser(
            [parsers[cast(str, parser_type)], MacroParser(type, node_type)]
        )
    return AlternativeParser(
        [MacroParser(type, node_type), parsers[cast(str, parser_type)]]
    )


def parse_typed_macro(stream: TokenStream):
    with stream.syntax(
        open_variable=r"\$\(", close_variable=r"\)", parser=r"\w+", colon=r":\s*"
    ):
        open_variable = stream.expect("open_variable")
        node: AstMacroLineVariable | AstInterpolation = delegate(
            "macro_line_variable", stream
        )

        parser = None
        if isinstance(node, AstMacroLineVariable):
            name = node.value

            if stream.get("colon"):
                parser = stream.expect("parser").value

        closed_variable = stream.expect("close_variable")
    return set_location(
        AstMacroArgument(name=name, parser=parser), open_variable, closed_variable
    )


def parse_coordinate(stream: TokenStream):
    with stream.syntax(modifier="[~^]"):
        modifier_token = stream.get("modifier")

        modifier = "absolute"

        if modifier_token and modifier_token.value == "~":
            modifier = "relative"
        elif modifier_token and modifier_token.value == "^":
            modifier = "local"

        macro: AstMacroArgument = delegate("typed_macro", stream)

        if macro.parser and macro.parser != "numeric":
            raise ValueError(
                f"Invalid macro type, received {macro.parser} expected numeric"
            )

        return set_location(
            AstMacroCoordinateArgument(
                name=macro.name, type=modifier, parser="numeric"
            ),
            modifier_token or macro.location,
            macro.end_location,
        )


@dataclass
class MacroNbtPathParser(NbtPathParser):
    """Parser for nbt paths."""

    def __call__(self, stream: TokenStream) -> AstNbtPath:
        components: List[Any] = []

        with stream.syntax(
            dot=r"\.",
            curly=r"\{|\}",
            bracket=r"\[|\]",
            quoted_string=r'"(?:\\.|[^\\\n])*?"' "|" r"'(?:\\.|[^\\\n])*?'",
            string=r"(?:[0-9a-z_\-]+:)?[a-zA-Z0-9_+-]+",
        ):
            components.extend(self.parse_modifiers(stream))

            while not components or stream.get("dot"):
                with stream.checkpoint() as commit:
                    macro: AstMacroArgument = delegate("typed_macro", stream)

                    if not macro.parser or macro.parser == "string":
                        components.append(
                            set_location(
                                AstMacroNbtPathKeyArgument(
                                    name=macro.name, parser="string"
                                ),
                                macro,
                            )
                        )
                    elif macro.parser == "nbt":
                        components.append(
                            set_location(
                                AstMacroNbtPathArgument(name=macro.name, parser="nbt"),
                                macro,
                            )
                        )

                    commit()

                if commit.rollback:
                    quoted_string, string = stream.expect("quoted_string", "string")

                    if quoted_string:
                        component_node = AstNbtPathKey(
                            value=self.quote_helper.unquote_string(quoted_string),
                        )
                        components.append(set_location(component_node, quoted_string))
                    elif string:
                        component_node = AstNbtPathKey(value=string.value)
                        components.append(set_location(component_node, string))

                components.extend(self.parse_modifiers(stream))

        if not components:
            raise stream.emit_error(InvalidSyntax("Empty nbt path not allowed."))

        node = AstNbtPath(components=AstChildren(components))
        return set_location(node, components[0], components[-1])


class MacroRangeParser:
    def get_bound(self, stream: TokenStream) -> int | float | AstMacroArgument | None:
        if number := stream.get("number"):
            return string_to_number(number.value)

        with stream.checkpoint() as commit:
            macro: AstMacroArgument = delegate("typed_macro", stream)

            if macro.parser and macro.parser != "numeric":
                raise ValueError(
                    f"Invalid macro type, received {macro.parser} expected numeric"
                )

            commit()

        if not commit.rollback:
            return macro

        return None

    def __call__(self, stream: TokenStream):
        with stream.syntax(range=r"\.\.", number=NUMBER_PATTERN):
            lower_bound = self.get_bound(stream)
            range = stream.get("range")
            upper_bound = self.get_bound(stream)

        return set_location(
            AstMacroRange(min=lower_bound, max=upper_bound),
            lower_bound or range or upper_bound,
            upper_bound or range or lower_bound,
        )


def get_parsers(parsers: dict[str, Parser]):
    parse_nbt: Parser = parsers["nbt"]

    make_nbt_parser = lambda parser: AlternativeParser(
        [MacroParser(("nbt", "string"), AstMacroNbtArgument), parser]
    )

    new_parsers = {
        "typed_macro": parse_typed_macro,
        "bool": macro(parsers, "bool"),
        "numeric": macro(parsers, "numeric"),
        "coordinate": AlternativeParser([parsers["coordinate"], parse_coordinate]),
        "time": macro(parsers, "time"),
        "word": macro(parsers, "word", priority=True),
        "phrase": macro(parsers, "phrase", priority=True),
        "greedy": macro(parsers, "greedy", priority=True),
        "entity": macro(parsers, "entity", priority=True),
        "nbt": make_nbt_parser(parsers["nbt"]),
        "nbt_compound_entry": make_nbt_parser(parsers["nbt_compound_entry"]),
        "nbt_list_or_array_element": make_nbt_parser(
            parsers["nbt_list_or_array_element"]
        ),
        "nbt_compound": make_nbt_parser(parsers["nbt_compound"]),
        "nbt_path": AlternativeParser(
            [parsers["nbt_path"], MacroNbtPathParser(nbt_compound_parser=parse_nbt)]
        ),
        "range": AlternativeParser([parsers["range"], MacroRangeParser()]),
    }

    if "bolt:literal" in parsers:
        new_parsers["bolt:literal"] = macro(
            parsers, "bolt:literal", node_type=AstMacroExpression
        )

    return new_parsers


@dataclass
class MacroConverter:
    base_converter: Callable[[Any, AstNode], AstNode]
    node_type: type

    def __call__(self, obj: Any, node: AstNode) -> AstNode:
        if isinstance(obj, StringWithMacro):
            return self.node_type.from_value(obj)
        return self.base_converter(obj, node)


conversions = {
    "interpolate_phrase": AstStringWithMacro,
    "interpolate_word": AstWordWithMacro,
    "interpolate_greedy": AstGreedyWithMacro,
    "interpolate_nbt": AstNbtValueWithMacro,
    "interpolate_message": AstMessageWithMacro,
}


def beet_default(ctx: Context):
    mc = ctx.inject(Mecha)

    mc.spec.parsers.update(get_parsers(mc.spec.parsers))
    mc.serialize.extend(CommandSerializer(spec=mc.spec))
    mc.steps.insert(0, MacroMutator())

    runtime = ctx.inject(Runtime)

    runtime.modules.codegen.extend(MacroCodegen())
    runtime.helpers["ast_to_macro"] = ast_to_macro
    runtime.helpers["make_macro_string"] = make_macro_string

    for conversion, node_type in conversions.items():
        runtime.helpers[conversion] = MacroConverter(
            runtime.helpers[conversion], node_type
        )
