"""
General utilities relating to text components. Includes the following:
- Color constants
- Helpers for building components within a theme
- etc.
"""

from minecraft_text_components import TextComponent, style, minify

SMALL_CAPS_MAP = {
    "a": "ᴀ",
    "b": "ʙ",
    "c": "ᴄ",
    "d": "ᴅ",
    "e": "ᴇ",
    "f": "ғ",
    "g": "ɢ",
    "h": "ʜ",
    "i": "ɪ",
    "j": "ᴊ",
    "k": "ᴋ",
    "l": "ʟ",
    "m": "ᴍ",
    "n": "ɴ",
    "o": "ᴏ",
    "p": "ᴘ",
    "q": "ᴏ̨",
    "r": "ʀ",
    "s": "s",
    "t": "ᴛ",
    "u": "ᴜ",
    "v": "ᴠ",
    "w": "ᴡ",
    "x": "x",
    "y": "ʏ",
    "z": "ᴢ",
}


class theme:
    primary = "#e7c8dd"
    secondary = "light_purple"
    body = "#ebebeb"
    success = "#7fb192"
    failure = "red"


def boxed_text(
    text: TextComponent,
    text_color: str = theme.primary,
    box_color: str = theme.secondary,
    variant: str = "[]",
):
    mid = len(variant) // 2
    first, second = variant[:mid], variant[mid:]
    return minify(
        [
            {"text": f"{first} ", "color": box_color},
            style(text, color=text_color),
            {"text": f" {second}", "color": box_color},
        ]
    )

def small_caps(text: str) -> str:
    """Converts a string to small caps."""
    
    return "".join(SMALL_CAPS_MAP.get(c, c) for c in text.lower())
