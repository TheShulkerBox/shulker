"""Preserve Bolt origins through helper calls and nested function assembly."""

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from itertools import count
from typing import Any, Generator, cast

from beet import Context, Function
from beet.core.utils import required_field
from bolt import Accumulator, Codegen, CodegenResult, Runtime
from jinja2 import Template
from mecha import (
    AbstractNode,
    AstChildren,
    AstCommand,
    AstNode,
    AstRoot,
    Mecha,
    MutatingReducer,
    rule,
)
from mecha.contrib.source_map import AstSourceMap, SourceMapSerializer
from mecha.contrib.source_map import SourceMapOptions as MechaSourceMapOptions
from tokenstream import SourceLocation


@dataclass(frozen=True)
class Source:
    resource_location: str | None
    filename: str | None
    block: int = 0
    lineno: int | None = field(default=None, compare=False)


class SourceMapOptions(MechaSourceMapOptions):
    header: str = (
        "# {{ compilation_unit.filename or compilation_unit.resource_location }}"
        "{% if compilation_unit.lineno %}:{{ compilation_unit.lineno }}{% endif %}"
    )


class TrackedLocation(SourceLocation):
    source: Source


class SourceTracker:
    def __init__(self, runtime: Runtime, mc: Mecha):
        self.runtime = runtime
        self.mc = mc
        self.blocks = count(1)

    def current_source(self) -> Source:
        unit = self.mc.database[self.mc.database.current]
        return Source(unit.resource_location, unit.filename)

    def get(self, node: AbstractNode) -> Source | None:
        if isinstance(node.location, TrackedLocation):
            return node.location.source
        return None

    def tag(self, node: AstNode, source: Source) -> AstNode:
        location = TrackedLocation(*node.location)
        location.source = source
        return replace(node, location=location)

    @contextmanager
    def capture(self, source: Source) -> Generator[None]:
        commands = self.runtime.commands
        start = len(commands)
        try:
            yield
        finally:
            if len(commands) > start:
                assign = AssignSource(tracker=self, source=source)
                commands[start:] = [
                    command if self.get(command) is not None else assign(command)
                    for command in commands[start:]
                ]


@dataclass
class AssignSource(MutatingReducer):
    tracker: SourceTracker = required_field()
    source: Source = required_field()
    use_node_line: bool = False

    @rule(AstNode)
    def assign_source(self, node: AstNode):
        if self.tracker.get(node) is not None:
            return node
        source = self.source
        if self.use_node_line and node.location.lineno:
            source = replace(source, lineno=node.location.lineno)
        return self.tracker.tag(node, source)


@dataclass(eq=False)
class SourceCodegen(Codegen):
    tracker: SourceTracker = required_field()

    def __call__(self, node: AstRoot) -> CodegenResult:
        unit = next(
            unit for unit in self.tracker.mc.database.values() if unit.ast is node
        )
        source = Source(unit.resource_location, unit.filename)
        node = AssignSource(tracker=self.tracker, source=source, use_node_line=True)(
            node
        )
        return super().__call__(node)

    def invoke(self, node: AbstractNode, *args: Any, **kwargs: Any) -> Any:
        acc: Accumulator = args[0]
        start = len(acc.statements)
        result = super().invoke(node, *args, **kwargs)
        source = self.tracker.get(node)
        if (
            source is not None
            and not isinstance(node, (AstCommand, AstRoot))
            and len(acc.statements) > start
        ):
            # Capture expressions without disturbing Bolt's control-flow blocks.
            acc.enclose(
                "with",
                acc.helper("source_map", acc.make_ref(source)),
                from_index=start,
            )
        return result


@dataclass
class AssignBlocks(MutatingReducer):
    tracker: SourceTracker = required_field()
    source: Source | None = field(default=None, init=False)
    block: int = field(default=0, init=False)

    def invoke(self, node: AbstractNode, *args: Any, **kwargs: Any) -> Any:
        previous_source, previous_block = self.source, self.block
        self.source = (
            self.tracker.get(node) or self.source or self.tracker.current_source()
        )
        if isinstance(node, AstRoot):
            self.block = next(self.tracker.blocks)
        try:
            return super().invoke(node, *args, **kwargs)
        finally:
            self.source, self.block = previous_source, previous_block

    @rule(AstNode)
    def assign_block(self, node: AstNode):
        assert self.source is not None
        source = replace(self.tracker.get(node) or self.source, block=self.block)
        if source.lineno is None and node.location.lineno:
            source = replace(source, lineno=node.location.lineno)
        if self.tracker.get(node) == source:
            return node
        return self.tracker.tag(node, source)


@dataclass
class PreserveSource(MutatingReducer):
    tracker: SourceTracker = required_field()

    @rule(AstNode)
    def preserve_source(self, node: AstNode):
        if self.tracker.get(node) is None:
            for parent in reversed(self.tracker.mc.transform.stack):
                if source := self.tracker.get(parent):
                    return self.tracker.tag(node, source)
        return node


@dataclass
class RenderSourceMap(MutatingReducer):
    tracker: SourceTracker = required_field()
    header_template: Template = required_field()

    def filter(self, node: AbstractNode) -> bool:
        return (
            isinstance(self.tracker.mc.database.current, Function)
            and isinstance(node, AstRoot)
            and bool(node.commands)
        )

    @rule(AstRoot)
    def source_map(self, node: AstRoot):
        if isinstance(node.commands[0], AstSourceMap):
            return node

        commands: list[AstCommand] = []
        previous = None
        for command in node.commands:
            source = next(
                (
                    source
                    for child in command.walk()
                    if (source := self.tracker.get(child))
                ),
                self.tracker.get(node) or self.tracker.current_source(),
            )
            if source != previous:
                header = self.header_template.render(
                    file_instance=self.tracker.mc.database.current,
                    compilation_unit=source,
                )
                commands.append(
                    AstSourceMap(header=("\n" if commands else "") + header)
                )
                previous = source
            commands.append(command)
        return replace(node, commands=AstChildren(commands))


def beet_default(ctx: Context):
    mc = ctx.inject(Mecha)
    runtime = ctx.inject(Runtime)
    opts = ctx.validate("source_map", SourceMapOptions)
    tracker = SourceTracker(runtime, mc)

    original = cast(Codegen, runtime.modules.codegen)
    codegen = SourceCodegen(
        tracker=tracker,
        accumulator_factory=original.accumulator_factory,
        finalizers=original.finalizers,
    )
    codegen.reset()
    codegen.extend(original)
    runtime.modules.codegen = codegen
    runtime.helpers["source_map"] = tracker.capture
    # Bolt's globals check invalidates code cached before provenance instrumentation.
    runtime.globals["_shulker_source_map_v3"] = True

    # Locations carry provenance without changing AST equality or function contents.
    mc.steps.insert(mc.steps.index(mc.transform), AssignBlocks(tracker=tracker))
    mc.transform.extend(PreserveSource(tracker=tracker))
    mc.steps.append(
        RenderSourceMap(
            tracker=tracker,
            header_template=ctx.template.compile(opts.header),
        )
    )
    mc.serialize.extend(SourceMapSerializer())
