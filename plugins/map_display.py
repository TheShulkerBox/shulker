"""Generate the rotating Summit map-display resource assets."""

from dataclasses import dataclass
import io
from pathlib import Path
import re

from beet import Context, ItemModel, Model, Texture
from PIL import Image, ImageDraw


BORDER_COLORS = ["#1C262A"] * 9
MAP_HEIGHT = 256
OPAQUE_WITHOUT_GLINT = 253
MAP_FILENAME = re.compile(r"^(?P<name>.+)_(?P<year>\d{4})$")
FLAT_TEMPLATE = "shulker:item/map_display/template"
FRAME_MODEL = "shulker:item/map_display/frame"
FRAME_ITEM_MODEL = "shulker:map_display/frame"
FRAME_TEXTURE = "shulker:item/map_display/frame_gray"
FRAME_LIGHT_EMISSION = 8
MAP_LIGHT_EMISSION = 15


def model_face(texture: str) -> dict:
    return {
        "uv": [0, 0, 16, 16],
        "texture": texture,
    }


def raised_frame_elements() -> list[dict]:
    # The map occupies [8, 8, 8] to [24, 17, 8]. The frame is 75% of the previous
    # width and only overlaps the baked nine-pixel border. The rest extends
    # outward so the frame doesn't hide map content. Full-height side rails own
    # all four corners so their exterior faces remain closed.
    border_overlap = 0.328125
    rail_width = 0.5625
    inner_min_x = 8 + border_overlap
    inner_max_x = 24 - border_overlap
    inner_min_y = 8 + border_overlap
    inner_max_y = 17 - border_overlap
    rail_min_x = inner_min_x - rail_width
    rail_max_x = inner_max_x + rail_width
    rail_min_y = inner_min_y - rail_width
    rail_max_y = inner_max_y + rail_width
    back_z = 8
    front_z = 8.5

    return [
        {
            "light_emission": FRAME_LIGHT_EMISSION,
            "from": [rail_min_x, rail_min_y, back_z],
            "to": [inner_min_x, rail_max_y, front_z],
            "faces": {
                "south": model_face("#frame"),
                "east": model_face("#frame"),
                "west": model_face("#frame"),
                "up": model_face("#frame"),
                "down": model_face("#frame"),
            },
        },
        {
            "light_emission": FRAME_LIGHT_EMISSION,
            "from": [inner_max_x, rail_min_y, back_z],
            "to": [rail_max_x, rail_max_y, front_z],
            "faces": {
                "south": model_face("#frame"),
                "east": model_face("#frame"),
                "west": model_face("#frame"),
                "up": model_face("#frame"),
                "down": model_face("#frame"),
            },
        },
        {
            "light_emission": FRAME_LIGHT_EMISSION,
            "from": [inner_min_x, inner_max_y, back_z],
            "to": [inner_max_x, rail_max_y, front_z],
            "faces": {
                "south": model_face("#frame"),
                "up": model_face("#frame"),
                "down": model_face("#frame"),
            },
        },
        {
            "light_emission": FRAME_LIGHT_EMISSION,
            "from": [inner_min_x, rail_min_y, back_z],
            "to": [inner_max_x, inner_min_y, front_z],
            "faces": {
                "south": model_face("#frame"),
                "up": model_face("#frame"),
                "down": model_face("#frame"),
            },
        },
    ]


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
            (width, MAP_HEIGHT), Image.Resampling.LANCZOS
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


def render_frame_texture() -> bytes:
    image = Image.new("RGBA", (16, 16), "#555B60")

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
    ctx.meta["map_display_frame_item_model"] = FRAME_ITEM_MODEL

    ctx.generate(FRAME_TEXTURE, Texture(render_frame_texture()))

    ctx.generate(
        FLAT_TEMPLATE,
        Model(
            {
                "textures": {"map": "#texture"},
                "elements": [
                    {
                        "light_emission": MAP_LIGHT_EMISSION,
                        "shade": False,
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

    ctx.generate(
        FRAME_MODEL,
        Model(
            {
                "textures": {
                    "frame": FRAME_TEXTURE,
                    "particle": "#frame",
                },
                "elements": raised_frame_elements(),
            }
        ),
    )
    ctx.generate(FRAME_ITEM_MODEL, item_model(FRAME_MODEL))

    for display_map, path in maps_by_path:
        resource = f"shulker:item/map_display/maps/{display_map.id}"
        ctx.generate(resource, Texture(render_map(path)))
        ctx.generate(
            resource,
            Model(
                {
                    "parent": FLAT_TEMPLATE,
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
