from beet import Context
from bolt import Module


def beet_default(ctx: Context):
    src = ctx.directory / "src"

    # Load our modules. we mount them directly to have a simpler path
    for dir in (src / "modules").iterdir():
        if dir.is_dir():
            ctx.data.mount(f"data/{dir.stem}/module", dir)
        else:
            ctx.data.mount(f"data/{dir.stem}/module/main.bolt", dir)

    # Lib gets loaded separately
    lib = src / "lib"
    ctx.data.mount("data/lib/module", lib)

    # prelude on its own
    ctx.generate("lib:prelude", Module(source_path=src / "prelude.bolt"))
