"""Register Shulker's booth definition in the compiled build context."""

from beet import Context
from summit.plugins.booths.booth_definition import BoothDefinition


def beet_default(ctx: Context):
    definition = ctx.directory / "src" / "summit" / "definition.json"
    ctx.data["shulker:definition"] = BoothDefinition(source_path=definition)
