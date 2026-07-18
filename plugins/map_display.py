"""Generate the rotating Summit map-display resource assets."""

from dataclasses import dataclass
import io
from pathlib import Path
import re

from beet import Context, ItemModel, Model, Texture
from PIL import Image, ImageDraw


BORDER_COLORS = [*(["#1C262A"] * 6), *(["#BA55D3"] * 3)]
MAP_HEIGHT = 512
OPAQUE_WITHOUT_GLINT = 253
MAP_FILENAME = re.compile(r"^(?P<name>.+)_(?P<year>\d{4})$")


@dataclass(frozen=True)
class DisplayMap:
    id: str
    name: str
    year: int

    @property
    def item_model(self) -> str:
        return f"shulker:map_display/{self.id}"


def parse_map(path: Path) -> DisplayMap:
    match = MAP_FILENAME.fullmatch(path.stem)
    if not match:
        raise ValueError(
            f"Map image {path.name!r} must end in a four-digit year, "
            "for example Market_2018.png."
        )

    source_name = match.group("name")
    map_id = re.sub(r"[^a-z0-9._-]+", "_", source_name.lower()).strip("_")
    return DisplayMap(
        id=map_id,
        name=source_name.replace("_", " ").title(),
        year=int(match.group("year")),
    )


def render_map(path: Path) -> bytes:
    with Image.open(path) as source:
        aspect_ratio = source.width / source.height
        width = max(16, int(MAP_HEIGHT * aspect_ratio) // 16 * 16)
        image = source.convert("RGBA").resize(
            (width, MAP_HEIGHT), Image.Resampling.NEAREST
        )

    draw = ImageDraw.Draw(image)
    for inset, color in enumerate(BORDER_COLORS):
        draw.rectangle(
            (inset, inset, image.width - inset - 1, image.height - inset - 1),
            outline=color,
        )

    alpha = image.getchannel("A")
    alpha = alpha.point(lambda value: OPAQUE_WITHOUT_GLINT if value == 255 else value)
    image.putalpha(alpha)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_branding(path: Path) -> bytes:
    with Image.open(path) as source:
        image = source.convert("RGBA")

    alpha = image.getchannel("A")
    alpha = alpha.point(lambda value: OPAQUE_WITHOUT_GLINT if value == 255 else value)
    image.putalpha(alpha)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def item_model(model: str) -> ItemModel:
    return ItemModel(
        {
            "model": {
                "type": "minecraft:model",
                "model": model,
            }
        }
    )


def beet_default(ctx: Context):
    source = ctx.directory / "src/summit/map_display/maps"
    map_paths = sorted(source.glob("*.png"))
    maps_by_path = [(parse_map(path), path) for path in map_paths]
    maps_by_path.sort(key=lambda entry: (entry[0].year, entry[0].name))

    if not maps_by_path:
        raise ValueError(f"No map display images found in {source}.")

    maps = [display_map for display_map, _ in maps_by_path]
    if len({display_map.id for display_map in maps}) != len(maps):
        raise ValueError("Map display image names must produce unique resource ids.")

    ctx.meta["map_display_maps"] = maps

    ctx.generate(
        "shulker:item/map_display/template",
        Model(
            {
                "textures": {"map": "#texture"},
                "elements": [
                    {
                        "from": [8, 8, 8],
                        "to": [24, 17, 8],
                        "faces": {
                            "south": {
                                "uv": [0, 0, 16, 16],
                                "texture": "#map",
                            }
                        },
                    }
                ],
            }
        ),
    )

    for display_map, path in maps_by_path:
        resource = f"shulker:item/map_display/maps/{display_map.id}"
        ctx.generate(resource, Texture(render_map(path)))
        ctx.generate(
            resource,
            Model(
                {
                    "parent": "shulker:item/map_display/template",
                    "textures": {"texture": resource},
                }
            ),
        )
        ctx.generate(
            display_map.item_model,
            item_model(resource),
        )

    branding = ctx.directory / "src/summit/assets"
    for name in ("icon", "logo"):
        model_resource = f"shulker:item/branding/{name}"
        ctx.generate(
            model_resource,
            Model(source_path=branding / f"models/item/branding/{name}.json"),
        )
        ctx.generate(
            model_resource,
            Texture(render_branding(branding / f"textures/item/branding/{name}.png")),
        )
        ctx.generate(
            f"shulker:branding/{name}",
            item_model(model_resource),
        )
