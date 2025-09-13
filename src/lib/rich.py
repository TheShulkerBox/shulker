from rich.console import Console, RenderableType
from rich.syntax import Syntax
from rich.panel import Panel
from rich.console import Group
from rich.tree import Tree
from rich.text import Text
from rich.theme import Theme

__all__ = [
    "Syntax",
    "Panel",
    "Group",
    "RenderableType",
    "Tree",
    "Text",
]

theme = Theme(
    {
        "header": "bold gray50",
        "body": "white",
        "secondary": "italic gray50",
        "x": "green",
    }
)

console = Console(theme=theme)
