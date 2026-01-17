from dataclasses import dataclass, field
from typing import Any, List, Literal
from beet import Context
from beet.core.utils import required_field
from bolt import AstInterpolation
from mecha import (
    NUMBER_PATTERN,
    AlternativeParser,
    AstChildren,
    AstCommand,
    AstMacroLineVariable,
    AstNbt,
    AstNbtCompound,
    AstNbtPath,
    AstNbtPathKey,
    AstNbtPathSubscript,
    AstNode,
    CommandSpec,
    Mecha,
    NbtParser,
    NbtPathParser,
    Parser,
    Visitor,
    delegate,
    rule,
)
from mecha.utils import string_to_number, number_to_string
from nbtlib import Base, Serializer as NbtSerializer
from tokenstream import InvalidSyntax, TokenStream, set_location



@dataclass
class MacroTag(Base):
    name: str = required_field()
    parser: str | None = required_field()

    def __post_init__(self):
        self.serializer = "macro"


def serialize_macro(self: NbtSerializer, tag: MacroTag):
    if tag.parser == "string":
        return f'"$({tag.name})"'

    return f"$({tag.name})"


@dataclass(frozen=True, slots=True)
class AstMacroArgument(AstNode):
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
class AstMacroArgument(AstMacroArgument): ...


@dataclass(frozen=True, slots=True)
class AstMacroRange(AstNode):
    min: int | float | AstMacroArgument | None = field(default=None)
    max: int | float | AstMacroArgument | None = field(default=None)


def nbt_contains_macro(root: dict | list):
    if isinstance(root, dict):
        for value in root.values():
            if nbt_contains_macro(value):
                return True

    elif isinstance(root, list):
        for value in root:
            if nbt_contains_macro(value):
                return True

    elif isinstance(root, MacroTag):
        return True

    return False


def path_contains_macro(path: AstNbtPath):
    for component in path.components:
        if isinstance(component, AstNbtPathSubscript) and component.index:
            if isinstance(component.index, AstNbtCompound) and nbt_contains_macro(
                component.index.evaluate()
            ):
                return True
            
            if isinstance(component.index, AstMacroArgument):
                return True

        if isinstance(component, AstNbtCompound) and nbt_contains_macro(
            component.evaluate()
        ):
            return True

    return False


@dataclass
class CommandSerializer(Visitor):
    spec: CommandSpec = required_field()

    @rule(AstCommand)
    def variable(self, node: AstCommand, result: list[str]):
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
                print(str(argument) + "\n")
                if isinstance(argument, AstNbt) and nbt_contains_macro(
                    argument.evaluate()
                ):
                    result[start_index] = "$"
                if isinstance(argument, AstNbtPath) and path_contains_macro(argument):
                    result[start_index] = "$"

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
    parser: str | tuple[str]
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
        return AlternativeParser([parsers[parser_type], MacroParser(type, node_type)])
    return AlternativeParser([MacroParser(type, node_type), parsers[parser_type]])


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


def modify_nbt(original_nbt: Parser) -> Parser:
    if isinstance(original_nbt, NbtParser):
        parse_nbt = AlternativeParser([MacroParser(("nbt", "string"), AstMacroNbtArgument), original_nbt])
        original_nbt.list_or_array_element_parser = parse_nbt
        original_nbt.recursive_parser = parse_nbt
        return parse_nbt

    elif isinstance(original_nbt, AlternativeParser):
        for alterative in original_nbt.parsers:
            if isinstance(alterative, NbtParser):
                return modify_nbt(alterative)
            else:
                modified = modify_nbt(alterative)
                if isinstance(modified, NbtParser):
                    return modified
                
        return original_nbt
    else:
        print(f"Warning! 'nbt' parser was not a NbtParser. Instead it was {type(original_nbt)}")
        return original_nbt
    

def get_parsers(parsers: dict[str, Parser]):
    parse_nbt: Parser = parsers["nbt"]

    parse_nbt = modify_nbt(parse_nbt)

    return {
        "typed_macro": parse_typed_macro,
        "bool": macro(parsers, "bool"),
        "numeric": macro(parsers, "numeric"),
        "coordinate": AlternativeParser([parsers["coordinate"], parse_coordinate]),
        "time": macro(parsers, "time"),
        "word": macro(parsers, "word", priority=True),
        "phrase": macro(parsers, "phrase", priority=True),
        "greedy": macro(parsers, "greedy", priority=True),
        "entity": macro(parsers, "entity", priority=True),
        # "nbt": parse_nbt,
        "nbt_path": AlternativeParser(
            [parsers["nbt_path"], MacroNbtPathParser(nbt_compound_parser=parse_nbt)]
        ),
        "range": AlternativeParser([parsers["range"], MacroRangeParser()]),
    }


NbtSerializer.serialize_macro = serialize_macro


def beet_default(ctx: Context):
    mc = ctx.inject(Mecha)

    mc.spec.parsers.update(get_parsers(mc.spec.parsers))
    mc.serialize.extend(CommandSerializer(spec=mc.spec))
