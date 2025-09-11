import importlib
from pathlib import Path
import sys

from beet import Context
from bolt import Module


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


def beet_default(ctx: Context):
    src = ctx.directory / "src"

    # We insert the src directory so that we can import as 'lib.text' instead of 'src.lib.text'
    sys.path.insert(0, str(src))

    # Load our modules. we mount them directly to have a simpler path
    for dir in src.iterdir():
        if dir.stem.startswith("."):
            continue

        if dir.is_dir():
            ctx.data.mount(f"data/{dir.stem}/module", dir)
        else:
            raise ValueError(
                f"{dir} is not a directory. Please place all modules within their own directory."
            )

        # For python files, we generate a bolt module that imports them
        for path in dir.glob("**/*.py"):
            bolt_path, module = generate_python_module(path)

            ctx.generate(f"{dir.stem}:{bolt_path}", module)
