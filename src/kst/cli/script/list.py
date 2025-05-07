import logging
from pathlib import Path
from typing import Annotated

import typer

from kst.cli.common import (
    ApiTokenOption,
    ExcludeOption,
    FormatOption,
    IncludeOption,
    KandjiTenantOption,
    OutputOption,
    RepoPathOption,
)
from kst.cli.utility import (
    api_config_prompt,
    filter_changes,
    format_list_table,
    format_plain_text_list,
    get_local_members,
    get_remote_members,
    validate_repo_path,
)
from kst.console import OutputConsole, OutputFormat, epilog_text
from kst.diff import ChangeType
from kst.repository import CustomScript, Repository, RepositoryDirectory

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")


# --- List Specific Options ---
LocalOnlyFlag = Annotated[
    bool,
    typer.Option(
        "--local",
        "-l",
        show_default=False,
        help="Only show local results.",
    ),
]
RemoteOnlyFlag = Annotated[
    bool,
    typer.Option(
        "--remote",
        "-r",
        show_default=False,
        help="Only show remote results.",
    ),
]


@app.command(name="list", epilog=epilog_text)
def list_scripts(
    local_only: LocalOnlyFlag = False,
    remote_only: RemoteOnlyFlag = False,
    include: IncludeOption = [],
    exclude: ExcludeOption = [],
    format: FormatOption = OutputFormat.TABLE,
    output: OutputOption = "-",  # type: ignore [reportArgumentType] "-" is understood by typer to mean stdout
    repo_str: RepoPathOption = ".",
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """List all custom scripts in the repository."""

    repo = validate_repo_path(repo=repo_str, subdir=RepositoryDirectory.SCRIPTS)

    # Check if local_only and remote_only flags are both included
    if local_only and remote_only:
        msg = "The -r/--remote and -l/--local flags cannot be included at the same time."
        console.error(msg)
        raise typer.BadParameter(msg)

    if not repo.is_dir():
        msg = f"The path provided for --repo option does not exist. (got {repo.resolve()})"
        console.error(msg)
        raise typer.BadParameter(msg)

    # Get remote scripts
    if local_only:
        remote_repo = Repository[CustomScript]()
    else:
        config = api_config_prompt(tenant_url, api_token)
        remote_repo = get_remote_members(config=config, member_type=CustomScript, all_members=True)

    # Get local scripts
    if remote_only:
        local_repo = Repository[CustomScript]()
    else:
        local_repo = get_local_members(repo=repo, member_type=CustomScript, all_members=True)

    # Compare local and remote scripts
    changes = filter_changes(local_repo=local_repo, remote_repo=remote_repo)

    # Filter included/exclude changes
    include_set = set(include) if include else set(ChangeType)  # All change types if not specified
    include_set -= set(exclude)  # Exclude any explicitly excluded change types
    changes = {change_type: change_list for change_type, change_list in changes.items() if change_type in include_set}

    if output == "-" and format is OutputFormat.TABLE:
        console.print(format_list_table(changes=changes, local_only=local_only, remote_only=remote_only))
    else:
        plain_output = format_plain_text_list(
            changes=changes, format=format, local_only=local_only, remote_only=remote_only
        )
        if output == "-":
            console.print_syntax(plain_output, syntax=format.to_syntax())
        else:
            output_path = Path(output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w") as output_file:
                output_file.write(plain_output)
