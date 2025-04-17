from beet import Context


def beet_default(ctx: Context):
    for dir in (ctx.directory / "src").iterdir():
        if dir.is_dir():
            ctx.data.mount(f"data/{dir.stem}/module", dir)
        else:
            ctx.data.mount(f"data/{dir.stem}/module/main.bolt", dir)
