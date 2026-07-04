"""Standardized result rendering for Keen modules.

This module owns the house style in one place so modules
only supply *data* (title + column headers + rows) and never
pick boxes/colors individually.

Usage (via ``BaseModule`` helpers, which also no-op in the web context):

    table = self.results_table("WAF Detection", ["Provider", "Method", "Evidence"])
    for row in rows:
        table.add_row(*row)
    self.render(table)

    detail = self.kv_table("WHOIS")
    detail.add_row("Registrar", registrar)
    self.render(detail)

    self.render(self.result_panel("3 accounts found", kind="success"))
"""

from typing import Iterable
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class Palette:
    """Single source of truth for semantic colors used across modules."""

    PRIMARY = "cyan"  # first/identifying column, table titles
    SECONDARY = "magenta"  # secondary attribute column
    VALUE = "white"  # generic values
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    MUTED = "dim"
    LINK = "green underline"


# House defaults, defined once.
_RESULTS_BOX = box.ROUNDED
_DETAIL_BOX = box.HORIZONTALS
_HEADER_STYLE = f"bold {Palette.PRIMARY}"
_TITLE_STYLE = f"bold {Palette.PRIMARY}"

# Border color per panel "kind".
_PANEL_BORDER = {
    "info": Palette.PRIMARY,
    "success": Palette.SUCCESS,
    "warn": Palette.WARNING,
    "error": Palette.ERROR,
}


def results_table(
    title: str | None = None,
    columns: Iterable = (),
) -> Table:
    """A standard results table.

    ``columns`` is an iterable of either column names (str) or ``(name, style)``
    tuples for callers that need a specific per-column color. When only names are
    given, the first column gets the primary color and the rest the value color.
    """
    table = Table(
        title=title,
        box=_RESULTS_BOX,
        show_header=True,
        header_style=_HEADER_STYLE,
        title_style=_TITLE_STYLE,
        show_lines=False,
        expand=True,
    )

    cols = list(columns)
    for idx, col in enumerate(cols):
        if isinstance(col, (tuple, list)):
            name, style = col[0], col[1]
        else:
            name = col
            style = Palette.PRIMARY if idx == 0 else Palette.VALUE
        table.add_column(str(name), style=style, overflow="fold")
    return table


def kv_table(title: str | None = None) -> Table:
    """A two-column key/value ("Property"/"Value") detail table."""
    table = Table(
        title=title,
        box=_DETAIL_BOX,
        show_header=False,
        title_style=_TITLE_STYLE,
        expand=True,
    )
    table.add_column("Property", style=Palette.PRIMARY, width=25, no_wrap=True)
    table.add_column("Value", style=Palette.VALUE, overflow="fold")
    return table


def result_panel(content, title: str | None = None, kind: str = "info") -> Panel:
    """A status/summary panel with a border color chosen from ``kind``."""
    border = _PANEL_BORDER.get(kind, Palette.PRIMARY)
    if isinstance(content, str):
        content = Text(content)
    return Panel(content, title=title, border_style=border, box=box.HEAVY)


def get_console() -> Console:
    """Factory for a Console (kept here so a plain/no-color mode can hook in)."""
    return Console()
