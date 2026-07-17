"""Mount locally generated data-pack resources below the shulker namespace."""

import re
from typing import Any

from beet import Context, Function, JsonFile


def beet_default(ctx: Context):
    generated_namespace = ctx.meta["generate_namespace"]
    source_roots = {
        path.name for path in (ctx.directory / "src").iterdir() if path.is_dir()
    }
    local_namespaces = source_roots | set(ctx.meta["local_resource_namespaces"])
    local_namespaces -= set(ctx.meta["provided_namespaces"])

    # This runs after Mecha/Bolt. At that point helpers such as FunctionPath and
    # loot-table generators have already created their resources, so an AST-only
    # import rewrite is no longer sufficient.
    pattern = re.compile(
        rf"(?<![\w.-])({'|'.join(sorted(local_namespaces, key=len, reverse=True))}):"
        r"([\w./-]+)"
    )

    def mount_reference(value: str) -> str:
        return pattern.sub(
            lambda match: f"{generated_namespace}:{match.group(1)}/{match.group(2)}",
            value,
        )

    def mount_json(value: Any) -> Any:
        if isinstance(value, str):
            return mount_reference(value)
        if isinstance(value, list):
            return [mount_json(item) for item in value]
        if isinstance(value, dict):
            return {key: mount_json(item) for key, item in value.items()}
        return value

    # Local code can already be in ``shulker`` while referring to a helper that
    # generated a resource beneath one of the aliases below. Rewrite references
    # in both places before moving the aliases' files.
    for namespace in local_namespaces | {generated_namespace}:
        if namespace not in ctx.data:
            continue

        for _, file in ctx.data[namespace].content:
            if isinstance(file, Function):
                file.lines[:] = [mount_reference(line) for line in file.lines]
            elif isinstance(file, JsonFile):
                file.data = mount_json(file.data)

    for namespace in local_namespaces:
        if namespace not in ctx.data:
            continue

        for path, file in list(ctx.data[namespace].content):
            ctx.data[f"{generated_namespace}:{namespace}/{path}"] = file

        del ctx.data[namespace]
