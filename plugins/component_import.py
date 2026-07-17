"""Generate a Bolt module that imports every custom component module."""

import importlib
from pathlib import Path

from beet import Context
from bolt import Module
from plugins.custom_load import LOCAL_IMPORT_PATTERN, resolve_import


def module_name(src: Path, path: Path) -> str:
    relative = path.relative_to(src).with_suffix("")
    return f"shulker:{'/'.join(relative.parts)}"


def make_python_module(src: Path, path: Path) -> Module:
    relative = path.relative_to(src).with_suffix("")
    python_module = importlib.import_module(".".join(relative.parts))
    names = ",\n    ".join(
        name for name in dir(python_module) if not name.startswith("_")
    )
    return Module(f"from {python_module.__name__} import {names}")


def beet_default(ctx: Context):
    src = ctx.directory / "src"
    components_dir = src / "component"
    all_components: list[str] = []
    seen: set[Path] = set()

    def mount(path: Path | None):
        if path is None or path in seen:
            return

        seen.add(path)
        if path.suffix == ".bolt":
            ctx.data[Module][module_name(src, path)] = Module(source_path=path)
            for match in LOCAL_IMPORT_PATTERN.finditer(path.read_text()):
                mount(resolve_import(src, path, match.group(1)))
        else:
            ctx.data[Module][module_name(src, path)] = make_python_module(src, path)

    # ``custom_load`` intentionally mounts only modules reachable from the
    # entrypoint graph.  ``component:all`` is generated before Bolt evaluates
    # that graph, so consulting ``ctx.data`` here can produce an empty module.
    # Discover the source files directly and mount each one before importing it.
    for path in sorted(components_dir.rglob("*")):
        if path.suffix not in {".bolt", ".py"} or path.name == "__init__.py":
            continue

        relative = path.relative_to(src).with_suffix("")
        if relative.parts == ("component", "type"):
            continue

        mount(path)
        all_components.append(module_name(src, path))

    ctx.data[Module]["shulker:component/all"] = Module(
        "\n".join(f"import {component} as _" for component in all_components)
    )
