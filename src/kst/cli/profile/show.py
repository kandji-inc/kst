import logging
from pathlib import Path
from typing import Annotated

import typer

from kst.cli.common import (
    ApiTokenOption,
    FormatOption,
    KandjiTenantOption,
    OutputOption,
    RepoPathOption,
)
from kst.cli.utility import api_config_prompt, get_member
from kst.console import OutputConsole, OutputFormat, epilog_text
from kst.repository import CustomProfile

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")


# --- Show Specific Options ---
ProfileOnlyOption = Annotated[
    bool, typer.Option("--profile", "-p", show_default=False, help="Only show the profile content.")
]
ProfileArgument = Annotated[
    str,
    typer.Argument(
        metavar="PROFILE",
        show_default=False,
        help="ID of or path to the profile to show",
    ),
]
RemoteOption = Annotated[
    bool,
    typer.Option(
        "--remote",
        "-r",
        show_default=False,
        help="Show remote profile instead of local version.",
    ),
]


@app.command(name="show", no_args_is_help=True, epilog=epilog_text)
# ruff: noqa: ARG001
def show_profile(
    profile_arg: ProfileArgument,
    remote: RemoteOption = False,
    profile_only: ProfileOnlyOption = False,
    format: FormatOption = OutputFormat.TABLE,
    output: OutputOption = "-",
    repo_str: RepoPathOption = ".",
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """Show details of a custom profile."""

    if remote:
        config = api_config_prompt(tenant_url, api_token)
    else:
        config = None
    profile = get_member(config=config, member_type=CustomProfile, key=profile_arg, repo=repo_str, remote=remote)  # type: ignore[reportPossiblyUnboundVariable]

    if output == "-" and format is OutputFormat.TABLE and not profile_only:
        console.print(profile.format_table())
    else:
        plain_output = (profile.profile if profile_only else profile).format_plain_text(format=format)
        if output == "-":
            console.print_syntax(plain_output, syntax=format.to_syntax())
        else:
            output_path = Path(output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w") as output_file:
                output_file.write(plain_output)
