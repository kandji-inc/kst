import logging
from pathlib import Path
from typing import Annotated

import typer

from kst import git
from kst.cli.common import (
    ActionType,
    ApiTokenOption,
    DryRunOption,
    ForceMode,
    KandjiTenantOption,
    OperationType,
    RepoPathOption,
)
from kst.cli.utility import (
    api_config_prompt,
    do_sync,
    filter_changes,
    get_local_members,
    get_remote_members,
    prepare_sync_actions,
    save_report,
    show_sync_report,
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


# --- Push Specific Options ---
ForceModeOption = Annotated[
    ForceMode,
    typer.Option(
        "--force-mode",
        "-m",
        help="Resolve conflicts using specified operation without prompting the user.",
    ),
]
CleanOption = Annotated[
    bool,
    typer.Option(
        "--clean",
        help="[red]Delete[/] remote scripts which are not present in the local repository.",
    ),
]


@app.command(name="sync", no_args_is_help=True, epilog=epilog_text)
def sync_scripts(
    repo_str: RepoPathOption = ".",
    paths_str: ScriptPathOption = [],
    script_ids: ScriptIdOption = [],
    all_scripts: ScriptAllOption = False,
    force_mode: ForceModeOption = ForceMode.SKIP,
    dry_run: DryRunOption = False,
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """Sync custom scripts with Kandji.

    Scripts to sync can be selected using any combination of the `--path` and
    `--id` options. Both `--path` and `--id` can be used multiple times as
    needed.

    If `--path` is used, Kandji scripts matching the ID of scripts at the
    provided path will be synced.

    If `--path is a directory, all scripts in the directory will included
    as if each was passed individually using `--path`.

    If `--all` is used, all scripts will be synced overriding other options.
    """

    repo = validate_repo_path(repo=repo_str, subdir=RepositoryDirectory.SCRIPTS)
    paths = [Path(path).expanduser().resolve() for path in paths_str]

    # Check if any scripts are selected
    if not (all_scripts or paths or script_ids):
        msg = "No scripts selected to push. Use --all, --path, or --id to select scripts."
        console.error(msg)
        raise typer.BadParameter(msg)

    if dry_run:
        console.print("Running in dry-run mode")

    # Ensure tenant URL and API token are provided
    config = api_config_prompt(tenant_url, api_token)

    # Convert script IDs to strings and remove any duplicates
    script_ids_set = set(map(str, script_ids))

    # Get scripts to push
    local_repo = get_local_members(
        repo=repo,
        member_type=CustomScript,
        all_members=all_scripts,
        member_paths=paths,
        member_ids=script_ids_set,
        raise_on_missing_id=False,
        raise_on_missing_path=True,
    )

    # Ensure all scripts requested by path are included in the ID set
    script_ids_set |= set(local_repo.keys())

    # Get remote scripts and don't raise on missing scripts since scripts may be local only
    remote_repo = get_remote_members(
        config=config,
        member_type=CustomScript,
        all_members=all_scripts,
        member_ids=script_ids_set,
        raise_on_missing=False,
    )

    # Exit with error if any scripts were not found
    verify_all_ids_found(member_ids=map(str, script_ids), local_repo=local_repo, remote_repo=remote_repo)

    # Compare local and remote scripts
    changes = filter_changes(local_repo=local_repo, remote_repo=remote_repo)

    # Prepare sync actions
    actions = prepare_sync_actions(changes=changes, force_mode=force_mode)

    if dry_run:
        for action in actions:
            console.print(
                f"Would have {action.action.past_tense()} script "
                f"{'locally' if action.operation is OperationType.PULL else 'in Kandji'}: "
                f"[yellow]{action.member.name}[/] ([yellow]{action.member.id}[/])"
            )
        if not actions:
            console.print("All specified scripts are already up to date.")
        console.print("Dry run complete. No changes were made.")
        return

    num_actions = len([action for action in actions if action.action is not ActionType.SKIP])
    if num_actions > 0:
        console.print(f"Syncing {num_actions} change{'s' if num_actions > 1 else ''} with Kandji...")

    # Commit changes before syncing
    try:
        git.commit_all_changes(cd_path=repo, message="Before syncing scripts with Kandji", scope=repo)
    except GitRepositoryError as error:
        console.print_error(f"Failed to commit changes to the local repository before sync: {error}")
        raise typer.Abort

    # Push changes to Kandji
    sync_results = do_sync(config=config, local_repo=local_repo, actions=actions)

    # Commit changes after sync
    try:
        git.commit_all_changes(cd_path=repo, message="After syncing scripts with Kandji", scope=repo)
    except GitRepositoryError:
        console.print_error(
            "Changes were synced successfully but not committed to the local repository. Please commit manually by running `git commit -am 'After syncing scripts with Kandji'`."
        )

    save_report(results=sync_results)

    # Show the sync report
    console.print("Sync operation complete!")
    show_sync_report(sync_results=sync_results, changes=changes, force_mode=force_mode)
