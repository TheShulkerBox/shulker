# bolt

"""
General utilities relating to text components. Includes the following:
- Color constants
- Helpers for building components within a theme
- etc.
"""

from minecraft_text_components import TextComponent, style, minify

class theme:
    primary = "#e7c8dd"
    secondary = "light_purple"
    body = "#ebebeb"
    success = "#7fb192"
    failure = "red"


def boxed_text(text: TextComponent, text_color: str, box_color: str):
    return minify(
        [
            {"text": "[ ", "color": box_color},
            style(text, color=text_color),
            {"text": " ]", "color": box_color},
        ]
    )
