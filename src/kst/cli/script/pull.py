import logging
from pathlib import Path
from typing import Annotated

import typer

from kst import git
from kst.cli.common import (
    ActionType,
    ApiTokenOption,
    DryRunOption,
    KandjiTenantOption,
    RepoPathOption,
)
from kst.cli.utility import (
    api_config_prompt,
    do_pulls,
    filter_changes,
    get_local_members,
    get_remote_members,
    prepare_pull_actions,
    save_report,
    show_pull_report,
    validate_repo_path,
    verify_all_ids_found,
)
from kst.console import OutputConsole, epilog_text
from kst.exceptions import GitRepositoryError
from kst.repository import CustomScript, RepositoryDirectory

from .common import (
    ScriptAllOption,
    ScriptIdOption,
    ScriptPathOption,
)

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")


# --- Pull Specific Options ---
ForceOption = Annotated[
    bool,
    typer.Option(
        "--force",
        help="[red]Overwrite[/] local changes instead of reporting conflicts.",
    ),
]
CleanOption = Annotated[
    bool,
    typer.Option(
        "--clean",
        help="[red]Delete[/] local scripts which are not present in Kandji.",
    ),
]


@app.command(name="pull", no_args_is_help=True, epilog=epilog_text)
def pull_scripts(
    repo_str: RepoPathOption = ".",
    paths_str: ScriptPathOption = [],
    script_ids: ScriptIdOption = [],
    all_scripts: ScriptAllOption = False,
    force: ForceOption = False,
    clean: CleanOption = False,
    dry_run: DryRunOption = False,
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """
    Pull remote custom scripts changes from Kandji.

    Scripts to pull can be selected using any combination of the --path and
    --id options. Both --path and --id can be used multiple times as needed. If
    --path is a directory, all scripts in the directory will included as if each
    was passed individually using --path.

    If --all is used, all scripts will be pulled overriding other options.

    If --force is used, local changes to the selected scripts will be ignored
    overwritten.

    If --clean is used, scripts will be deleted from the local repository if they
    are not in Kandji. --clean can only be used with --all.

    """

    repo = validate_repo_path(repo=repo_str, subdir=RepositoryDirectory.SCRIPTS)
    paths = [Path(path).expanduser().resolve() for path in paths_str]

    # Check if --clean is used without --all
    if clean and not all_scripts:
        msg = "The --clean option can only be used with --all"
        console.error(msg)
        raise typer.BadParameter(msg)

    # Check if any scripts are selected
    if not (all_scripts or paths or script_ids):
        msg = "No scripts selected to pull. Use --all, --path, or --id to select scripts."
        console.error(msg)
        raise typer.BadParameter(msg)

    if dry_run:
        console.print("Running in dry-run mode")

    # Ensure tenant URL and API token are provided
    config = api_config_prompt(tenant_url, api_token)

    # Convert script IDs to strings and remove any duplicates
    script_ids_set = set(map(str, script_ids))

    # Get scripts to pull
    local_repo = get_local_members(
        repo=repo,
        member_type=CustomScript,
        all_members=all_scripts,
        member_paths=paths,
        member_ids=script_ids_set,
        raise_on_missing_id=False,  # IDs may be remote only so don't raise
        raise_on_missing_path=True,  # path lookup is local only, so raise if not found
    )

    # Ensure all scripts requested by path are included in the ID set
    script_ids_set |= set(local_repo.keys())

    # Get remote scripts
    remote_repo = get_remote_members(
        config=config,
        member_type=CustomScript,
        all_members=all_scripts,
        member_ids=script_ids_set,
        raise_on_missing=False,  # If a script was specified by ID and was not found in either repo, raise
    )

    # Exit with error if any scripts were not found
    verify_all_ids_found(member_ids=map(str, script_ids), local_repo=local_repo, remote_repo=remote_repo)

    # Compare local and remote scripts
    changes = filter_changes(local_repo=local_repo, remote_repo=remote_repo)

    # Prepare pull actions
    actions = prepare_pull_actions(changes=changes, force_pull=force, allow_delete=clean)

    if dry_run:
        for action in actions:
            console.print(
                f"Would have {action.action.past_tense()} script: [yellow]{action.member.name}[/] ([yellow]{action.member.id}[/])"
            )

        if not actions:
            console.print("All specified scripts are already up to date.")
        console.print("Dry run complete. No changes were made.")
        return

    num_actions = len([action for action in actions if action.action is not ActionType.SKIP])
    if num_actions > 0:
        console.print(f"Pulling {num_actions} change{'s' if num_actions > 1 else ''} from Kandji...")

    # Commit changes before pulling
    try:
        git.commit_all_changes(cd_path=repo, message="Before pulling scripts from Kandji", scope=repo)
    except GitRepositoryError as error:
        console.print_error(f"Failed to commit changes to the local repository before pull: {error}")
        raise typer.Abort

    # Pull changes to Kandji
    pull_results = do_pulls(local_repo=local_repo, actions=actions)

    # Commit changes after pulling
    try:
        git.commit_all_changes(cd_path=repo, message="After pulling scripts from Kandji", scope=repo)
    except GitRepositoryError:
        console.print_error(
            "Changes were pulled successfully but not committed to the local repository. Please commit manually by running `git commit -am 'After pulling scripts to Kandji'`."
        )

    save_report(results=pull_results)

    # Show the pull report
    console.print("Pull operation complete!")
    show_pull_report(pull_results=pull_results, changes=changes, force_pull=force, allow_delete=clean)
