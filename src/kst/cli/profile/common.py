import logging
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import typer

from kst.console import OutputConsole

console = OutputConsole(logging.getLogger(__name__))

# --- Shared Options ---
# General Options Panel
CleanOption = Annotated[
    bool,
    typer.Option(
        "--clean",
        help="Remove profiles deleted since last sync.",
    ),
]

# Profile Selection Panel
ProfilePathOption = Annotated[
    list[str],
    typer.Option(
        "--path",
        show_default=False,
        rich_help_panel="Profile Selection",
        metavar="PATH",
        help="Include profile(s) at path.",
    ),
]
ProfileIdOption = Annotated[
    list[UUID],
    typer.Option(
        "--id",
        show_default=False,
        rich_help_panel="Profile Selection",
        help="Include profile with ID.",
    ),
]
ProfileAllOption = Annotated[
    bool,
    typer.Option(
        "--all",
        rich_help_panel="Profile Selection",
        help="Include all profiles.",
    ),
]


# --- Shared Data Objects ---
class RunsOn(StrEnum):
    MAC = "mac"
    IPHONE = "iphone"
    IPAD = "ipad"
    TV = "tv"
    VISION = "vision"
    ALL = "all"
