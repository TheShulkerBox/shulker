"""Load Summit's complete core data and resource packs into this build."""

from beet import Context


def beet_default(ctx: Context):
    core = ctx.directory.parent / "Smithed" / "summit-26" / "summit" / "core"
    ctx.data.load(core)
    ctx.assets.load(core)
