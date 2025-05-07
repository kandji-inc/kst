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
from kst.repository import CustomScript

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")


# --- Show Specific Options ---
AuditOnlyOption = Annotated[
    bool, typer.Option("--audit", "-a", show_default=False, help="Only show the audit script content.")
]
RemediationOnlyOption = Annotated[
    bool,
    typer.Option("--remediation", "-k", show_default=False, help="Only show the remediation script content."),
]
ScriptArgument = Annotated[
    str,
    typer.Argument(
        metavar="SCRIPT",
        show_default=False,
        help="ID of or path to the script to show",
    ),
]
RemoteOption = Annotated[
    bool,
    typer.Option(
        "--remote",
        "-r",
        show_default=False,
        help="Show remote script instead of local version.",
    ),
]


@app.command(name="show", no_args_is_help=True, epilog=epilog_text)
# ruff: noqa: ARG001
def show_script(
    script_arg: ScriptArgument,
    remote: RemoteOption = False,
    audit_only: AuditOnlyOption = False,
    remediation_only: RemediationOnlyOption = False,
    format: FormatOption = OutputFormat.TABLE,
    output: OutputOption = "-",
    repo_str: RepoPathOption = ".",
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """Show details of a custom script."""

    if audit_only and remediation_only:
        msg = "--audit-only and --remediation-only are mutually exclusive. Please choose one."
        console.error(msg)
        raise typer.BadParameter(msg)

    if remote:
        config = api_config_prompt(tenant_url, api_token)
    else:
        config = None
    script = get_member(config=config, member_type=CustomScript, key=script_arg, repo=repo_str, remote=remote)  # type: ignore[reportPossiblyUnboundVariable]

    if output == "-":
        if audit_only:
            console.print_syntax(script.audit.content)
        elif remediation_only:
            console.print_syntax(script.remediation.content if script.remediation else "")
        elif format == OutputFormat.TABLE:
            console.print(script.format_table())
        else:
            console.print_syntax(script.format_plain_text(format), syntax=format.to_syntax())
    else:
        if audit_only:
            plain_output = script.audit.content
        elif remediation_only:
            plain_output = script.remediation.content if script.remediation else ""
        else:
            plain_output = script.format_plain_text(format)

        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as output_file:
            output_file.write(plain_output)
