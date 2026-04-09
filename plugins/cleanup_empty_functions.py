from beet import Context


def beet_default(ctx: Context):
    for path in ctx.data.functions.match("*"):
        if len(ctx.data.functions[path].lines) == 0:
            ctx.data.functions.pop(path)
