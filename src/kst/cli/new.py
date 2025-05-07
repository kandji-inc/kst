import logging
import shutil
from importlib.resources import read_text
from pathlib import Path
from typing import Annotated

import typer

from kst import git
from kst.console import OutputConsole, epilog_text
from kst.exceptions import GitRepositoryError, InvalidRepositoryError
from kst.repository import RepositoryDirectory

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")

readme_text = read_text("kst.cli._resources", "new_repo_readme.md")
macos_gitignore_text = read_text("kst.cli._resources", "gitignore.txt")

PathOption = Annotated[
    str,
    typer.Argument(
        metavar="PATH",
        resolve_path=True,
        show_default=False,
        help="A Path to the directory where the new repository should be initialized.",
    ),
]


@app.command(name="new", epilog=epilog_text, no_args_is_help=True)
def new_repo(path_str: PathOption):
    """Create a new repository"""

    # Check if the path already exists and raise an error if it does.
    path = Path(path_str).expanduser().resolve()
    if path.exists():
        msg = f"Path {path} already exists."
        console.error(msg)
        raise typer.BadParameter(msg)

    # Check to make sure that the path is not already in a git repository.
    try:
        root = git.locate_root(cd_path=path, check_marker=False)
    except InvalidRepositoryError:
        pass
    else:
        msg = f"The parent path {root} is already a git repository. Please choose another path."
        console.error(msg)
        raise typer.BadParameter(msg)

    # Create the directory and initial files.
    path.mkdir(parents=True)
    (path / ".kst").touch()
    (path / "README.md").write_text(readme_text)
    (path / ".gitignore").write_text(macos_gitignore_text)
    (path / RepositoryDirectory.PROFILES).mkdir()
    (path / RepositoryDirectory.SCRIPTS).mkdir()

    # Initialize the git repository and commit all files.
    try:
        git.git("init", cd_path=path, expected_exit_code=0)
        git.commit_all_changes(cd_path=path, message="Initial commit")
    except FileNotFoundError:
        console.print_error(
            "A suitable Git executable was not found. Git is required for managing a kst repo. Please ensure Git is installed."
        )
        shutil.rmtree(path)
        raise typer.Exit(code=1)
    except GitRepositoryError:
        console.print_error("Failed to initialize the repository. Please check the log for more information.")
        shutil.rmtree(path)
        raise typer.Exit(code=1)

    console.print_success(f"Created a new kst repository at {path}")
    console.print("Check out the included README.md file for more information on getting started.")
