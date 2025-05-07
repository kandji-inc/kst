import logging
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
        help="Remove scripts deleted since last sync.",
    ),
]

# Script Selection Panel
ScriptPathOption = Annotated[
    list[str],
    typer.Option(
        "--path",
        show_default=False,
        rich_help_panel="Script Selection",
        help="Include script(s) at path.",
    ),
]
ScriptIdOption = Annotated[
    list[UUID],
    typer.Option(
        "--id",
        show_default=False,
        rich_help_panel="Script Selection",
        help="Include script with ID.",
    ),
]
ScriptAllOption = Annotated[
    bool,
    typer.Option(
        "--all",
        rich_help_panel="Script Selection",
        help="Include all scripts.",
    ),
]
