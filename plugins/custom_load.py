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
            return path

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


def beet_default(ctx: Context):
    src = ctx.directory / "src"

    # We insert the src directory so that we can import as 'lib.text' instead of 'src.lib.text'
    sys.path.insert(0, str(src))

    for dir in src.iterdir():
        if not dir.is_dir():
            raise ValueError(
                f"{dir} is not a directory. Please place all modules within their own directory."
            )

    bolt_meta = ctx.meta.get("bolt", {})
    queue = [
        resolve_import(src, src / "dummy.bolt", prelude)
        for prelude in bolt_meta.get("prelude", [])
    ]
    queue.extend(seed_entrypoints(src, bolt_meta.get("entrypoint", "*")))
    seen: set[Path] = set()

    # Only load the summit entrypoint graph. Dead modules in this repo are allowed to be cursed.
    while queue:
        path = queue.pop()

        if path is None or path in seen or "__testing__" in path.parts:
            continue

        seen.add(path)
        key = module_path(src, path)

        if path.suffix == ".py":
            _, module = generate_python_module(path)
            ctx.data[Module][key] = module
            continue

        ctx.data[Module][key] = Module(source_path=path)

        for match in LOCAL_IMPORT_PATTERN.finditer(path.read_text()):
            queue.append(resolve_import(src, path, match.group(1)))
