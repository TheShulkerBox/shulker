import importlib
from pathlib import Path
import re
import sys

from beet import Context
from bolt import Module

LOCAL_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*:[^\s]+|\.+[^\s]*)",
    re.MULTILINE,
)


def generate_python_module(path: Path) -> tuple[str, Module]:
    src_index = path.parts.index("src")
    parts = path.parts[src_index + 1 : -1] + (path.stem,)
    import_path = ".".join(parts)
    bolt_path = "/".join(parts[1:])

    python_module = importlib.import_module(import_path)
    names = ",\n    ".join(
        name for name in dir(python_module) if not name.startswith("_")
    )
    contents = f"from {import_path} import {names}"

    return bolt_path, Module(contents)


def module_path(src: Path, path: Path) -> str:
    parts = path.relative_to(src).with_suffix("").parts
    return f"shulker:{'/'.join(parts)}"


def resolve_import(src: Path, current: Path, spec: str) -> Path | None:
    current_parts = list(current.relative_to(src).with_suffix("").parts)

    if spec.startswith("."):
        dots = len(spec) - len(spec.lstrip("."))
        rest = spec[dots:].lstrip("/")
        parts = current_parts[:-1]

        for _ in range(dots - 1):
            if parts:
                parts.pop()

        if rest:
            parts.extend(rest.split("/"))

    elif ":" in spec:
        namespace, rest = spec.split(":", 1)

        if namespace == "shulker":
            parts = rest.split("/")
        else:
            parts = [namespace, *rest.split("/")]

    else:
        return None

    for suffix in (".bolt", ".py"):
        path = src.joinpath(*parts).with_suffix(suffix)
        if path.exists():
            # Relative imports can leave ``..`` in the path. Normalize it before
            # deriving Python import names or data-pack module keys.
            return path.resolve()

    return None


def seed_entrypoints(src: Path, entrypoint: str | list[str]) -> list[Path]:
    entries = entrypoint if isinstance(entrypoint, list) else [entrypoint]
    paths: list[Path] = []

    for entry in entries:
        namespace, _, rest = entry.partition(":")

        if namespace == "shulker":
            glob = rest.replace("*", "**/*.bolt")
        elif rest == "*":
            glob = f"{namespace}/**/*.bolt"
        else:
            glob = f"{namespace}/{rest}.bolt"

        paths.extend(path for path in src.glob(glob) if path.is_file())

    return paths


def source_modules(src: Path) -> list[Path]:
    """Return every importable source module, independent of the entrypoint graph."""
    return sorted(
        path
        for path in src.rglob("*")
        if path.suffix in (".bolt", ".py") and path.name != "__init__.py"
    )


def beet_default(ctx: Context):
    src = ctx.directory / "src"

    # We insert the src directory so that we can import as 'lib.text' instead of 'src.lib.text'
    sys.path.insert(0, str(src))

    for dir in src.iterdir():
        if not dir.is_dir():
            raise ValueError(
                f"{dir} is not a directory. Please place all modules within their own directory."
            )

    # Mount every source module. ``bolt.entrypoint`` still decides which modules
    # are evaluated, but mounting must not depend on the import graph: registries
    # such as ``component:all`` need access to every module before evaluation.
    for path in source_modules(src):
        key = module_path(src, path)

        if path.suffix == ".py":
            _, module = generate_python_module(path)
            ctx.data[Module][key] = module
            continue

        ctx.data[Module][key] = Module(source_path=path)
