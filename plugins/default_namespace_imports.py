"""Mount local Bolt resource locations through the generated namespace.

For example, ``from lib:item import Item`` is parsed as an import of
``shulker:lib/item``. Local resource aliases are mounted too, while namespaces
provided by Minecraft and the vendored core data pack remain unchanged.
"""

from dataclasses import dataclass, replace

from beet import Context
from bolt import AstFromImport
from mecha import AstCommand, AstResourceLocation, Mecha, MutatingReducer, Parser, rule


def beet_default(ctx: Context):
    """Install the resolver after Bolt has registered its import parser."""
    source_roots = frozenset(
        path.name for path in (ctx.directory / "src").iterdir() if path.is_dir()
    )
    mounted_namespaces = source_roots | set(ctx.meta["local_resource_namespaces"])
    mounted_namespaces -= set(ctx.meta["provided_namespaces"])
    namespace = ctx.meta["generate_namespace"]
    mc = ctx.inject(Mecha)

    mc.spec.parsers["bolt:import"] = DefaultNamespaceImportParser(
        parser=mc.spec.parsers["bolt:import"],
        namespace=namespace,
        source_roots=mounted_namespaces,
    )
    # Bolt evaluates modules before Mecha's normal transform phase. Insert this
    # reducer ahead of Bolt's evaluator so cached ASTs are normalized as well.
    mc.steps.insert(
        0,
        DefaultNamespaceImportTransformer(
            namespace=namespace,
            source_roots=mounted_namespaces,
        ),
    )


@dataclass
class DefaultNamespaceImportParser:
    """Map local import aliases to the pack namespace."""

    parser: Parser
    namespace: str
    source_roots: frozenset[str]

    def __call__(self, stream) -> AstResourceLocation:
        node: AstResourceLocation = self.parser(stream)
        return resolve_import(node, self.namespace, self.source_roots)


class DefaultNamespaceImportTransformer(MutatingReducer):
    """Normalize local locations before Bolt evaluates a module."""

    def __init__(self, namespace: str, source_roots: frozenset[str]):
        super().__init__()
        self.namespace = namespace
        self.source_roots = source_roots

    @rule(AstCommand, identifier="import:module")
    @rule(AstCommand, identifier="import:module:as:alias")
    @rule(AstFromImport)
    def transform_import(self, node: AstCommand):
        module = node.arguments[0]
        if not isinstance(module, AstResourceLocation):
            return node

        resolved = resolve_import(module, self.namespace, self.source_roots)
        if resolved is module:
            return node

        return replace(node, arguments=type(node.arguments)([resolved, *node.arguments[1:]]))

    @rule(AstResourceLocation)
    def transform_resource_location(self, node: AstResourceLocation):
        """Mount local function, tag, loot-table, and similar resource IDs."""
        return resolve_import(node, self.namespace, self.source_roots)


def resolve_import(
    node: AstResourceLocation,
    namespace: str,
    source_roots: frozenset[str],
) -> AstResourceLocation:
    if node.namespace in source_roots:
        return replace(
            node,
            namespace=namespace,
            path=f"{node.namespace}/{node.path}",
        )

    return node
