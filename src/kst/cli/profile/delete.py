import logging
from pathlib import Path
from typing import Annotated

import typer

from kst import git
from kst.api import ApiConfig
from kst.cli.common import (
    ApiTokenOption,
    DryRunOption,
    KandjiTenantOption,
    OperationType,
    RepoPathOption,
)
from kst.cli.utility import (
    api_config_prompt,
    do_sync,
    get_local_members,
    get_remote_members,
    prepare_delete_actions,
    save_report,
    show_delete_report,
    validate_repo_path,
    verify_all_ids_found,
)
from kst.console import OutputConsole, epilog_text
from kst.exceptions import GitRepositoryError
from kst.repository import CustomProfile, Repository, RepositoryDirectory

from .common import (
    ProfileAllOption,
    ProfileIdOption,
    ProfilePathOption,
)

__all__ = ["app"]

console = OutputConsole(logging.getLogger(__name__))

app = typer.Typer(rich_markup_mode="rich")


# --- Delete Specific Options ---
LocalOnlyFlag = Annotated[
    bool,
    typer.Option(
        "--local",
        "-l",
        show_default=False,
        help="Only delete local version.",
    ),
]
RemoteOnlyFlag = Annotated[
    bool,
    typer.Option(
        "--remote",
        "-r",
        show_default=False,
        help="Only delete remote version.",
    ),
]
ForceOption = Annotated[
    bool,
    typer.Option(
        "--force",
        "-f",
        help="[red]Delete profiles without prompting for confirmation.[/]",
    ),
]


@app.command("delete", epilog=epilog_text, no_args_is_help=True)
def delete(
    paths_str: ProfilePathOption = [],
    profile_ids: ProfileIdOption = [],
    all_profiles: ProfileAllOption = False,
    local_only: LocalOnlyFlag = False,
    remote_only: RemoteOnlyFlag = False,
    force: ForceOption = False,
    repo_str: RepoPathOption = ".",
    dry_run: DryRunOption = False,
    tenant_url: KandjiTenantOption = None,
    api_token: ApiTokenOption = None,
):
    """[red]Delete[/] profiles from your local repository or Kandji."""

    repo = validate_repo_path(repo=repo_str, subdir=RepositoryDirectory.PROFILES)
    paths = [Path(path).expanduser().resolve() for path in paths_str]

    # Check if any profiles are selected
    if not (all_profiles or paths or profile_ids):
        msg = "No profiles selected to delete. Use --all, --path, or --id to select profiles."
        console.error(msg)
        raise typer.BadParameter(msg)

    # Check if local_only and remote_only flags are both included
    if local_only and remote_only:
        msg = "The -r/--remote and -l/--local flags cannot be included at the same time."
        console.error(msg)
        raise typer.BadParameter(msg)

    if not repo.is_dir():
        msg = f"The path provided for --repo option does not exist. (got {repo.resolve()})"
        console.error(msg)
        raise typer.BadParameter(msg)

    if dry_run:
        console.print("Running in dry-run mode")

    # Convert profile IDs to strings and remove any duplicates
    profile_ids_set = set(map(str, profile_ids))

    # Get local profiles
    local_repo = get_local_members(
        repo=repo,
        member_type=CustomProfile,
        member_paths=paths,
        member_ids=profile_ids_set,
        all_members=all_profiles,
        raise_on_missing_id=False,
        raise_on_missing_path=True,
    )

    # Include any profiles from the local repo that were explicitly requested by ID
    # Also ensure all profiles requested by path are included in the ID set
    profile_ids_set |= set(local_repo.keys())

    # Get remote profiles
    if local_only:
        config = ApiConfig(tenant_url="http://xxxxxxxx.api.kandji.io", api_token="00000000-0000-0000-0000-000000000000")
        remote_repo = Repository[CustomProfile]()
    else:
        config = api_config_prompt(tenant_url, api_token)
        remote_repo = get_remote_members(
            config=config,
            member_type=CustomProfile,
            all_members=all_profiles,
            member_ids=profile_ids_set,
            raise_on_missing=False,
        )

    # Include any profiles from the remote repo that were not explicitly requested by ID
    if remote_only:
        profile_ids_set = set(remote_repo.keys())
    else:
        profile_ids_set |= set(remote_repo.keys())

    # Exit with error if any profiles were not found
    verify_all_ids_found(
        member_ids=map(str, profile_ids),
        local_repo=local_repo,
        remote_repo=remote_repo,
        local_only=local_only,
        remote_only=remote_only,
    )

    # Prepare delete actions
    actions = prepare_delete_actions(
        local_repo=local_repo,
        remote_repo=remote_repo,
        member_ids=profile_ids_set,
        local_only=local_only,
        remote_only=remote_only,
    )

    if dry_run:
        for action in actions:
            console.print(
                f"Would have deleted profile "
                f"{'locally' if action.operation is OperationType.PULL else 'in Kandji'}: "
                f"[yellow]{action.member.name} ({action.member.id}[/])"
            )
        if not actions:
            console.print("Nothing was selected for deletion.")
        console.print("Dry run complete. No changes were made.")
        return

    if not force:
        for action in actions:
            console.print(
                f"Will delete profile "
                f"{'locally' if action.operation is OperationType.PULL else 'in Kandji'}: "
                f"[yellow]{action.member.name} ({action.member.id})[/]",
                style="bold red",
            )
        if actions:
            if typer.confirm("Do you want to continue?", abort=True):
                console.print("Confirmed.")

    if len(profile_ids_set) > 0:
        console.print(f"Deleting {len(profile_ids_set)} profile{'s' if len(profile_ids_set) > 1 else ''}...")

    # Commit changes before deleting
    try:
        git.commit_all_changes(cd_path=repo, message="Before syncing profiles with Kandji", scope=repo)
    except GitRepositoryError as error:
        console.print_error(f"Failed to commit changes to the local repository before sync: {error}")
        raise typer.Abort

    results = do_sync(config=config, local_repo=local_repo, actions=actions, description="Deleting profiles")

    # Commit changes after deleting
    try:
        git.commit_all_changes(cd_path=repo, message="After syncing profiles with Kandji", scope=repo)
    except GitRepositoryError:
        console.print_error(
            "Changes were synced successfully but not committed to the local repository. Please commit manually by running `git commit -am 'After syncing profiles with Kandji'`."
        )

    save_report(results=results)

    # Show the delete report
    if actions:
        console.print("Delete operation complete!")
    show_delete_report(sync_results=results)
