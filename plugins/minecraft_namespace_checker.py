from beet import Context, TagFile
from beet.contrib.vanilla import Vanilla


class OverridingMinecraftFile(Exception): ...


def beet_default(ctx: Context):
    vanilla = ctx.inject(Vanilla)
    vanilla.minecraft_version = "1.21"

    for file_type, paths in ctx.query(match="minecraft:*").items():
        for (path, file), _ in paths.items():
            if isinstance(file, TagFile):
                continue
                
            if path not in vanilla.data[file_type]:
                raise OverridingMinecraftFile(
                    f"Likely misspelled var name: {path[10:]} from file"
                )
