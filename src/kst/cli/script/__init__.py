import logging

import typer

from kst import git
from kst.console import OutputConsole

from .delete import app as delete_app
from .list import app as list_app
from .new import app as new_app
from .pull import app as pull_app
from .push import app as push_app
from .show import app as show_app
from .sync import app as sync_app

console = OutputConsole(logging.getLogger(__name__))

__all__ = ["app"]


def callback():
    """Execute initialization steps for all script commands."""

    # Ensure the git executable is available for all commands
    try:
        git.locate_git()
    except FileNotFoundError as error:
        console.print_error("Unable to locate the `git` executable")
        console.print_error("Please make sure `git` is installed and available in your PATH.", style="none")
        raise typer.Exit(code=1) from error


app = typer.Typer(callback=callback, rich_markup_mode="rich")
app.add_typer(new_app)
app.add_typer(list_app)
app.add_typer(show_app)
app.add_typer(delete_app)
app.add_typer(push_app)
app.add_typer(pull_app)
app.add_typer(sync_app)
