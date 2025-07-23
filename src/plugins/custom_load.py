from beet import Context
from bolt import Module
from dotenv import dotenv


def beet_default(ctx: Context):
    dotenv.load_dotenv()
    
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

    # For python files that start with `# bolt`, re-export as bolt file
    # ⚠️ python file should *also* be a valid bolt file (no list comprehensions, match statements etc) 
    for python_file in lib.glob("*.py"):
        with python_file.open() as f:
            if f.readline().startswith("# bolt"):
                ctx.generate(f"lib:{python_file.stem}", Module(source_path=python_file))

    # We load prelude on it's own since it's ✨ special ✨
    ctx.generate("lib:prelude", Module(source_path=src / "prelude.bolt"))
