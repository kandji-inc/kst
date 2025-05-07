import contextlib
import io
import json
import logging
import plistlib
import shutil
from collections import Counter, OrderedDict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from uuid import UUID

import platformdirs
import requests
import typer
from pydantic import ValidationError
from rich import box
from rich.progress import track
from rich.table import Table

from kst import git
from kst.__about__ import APP_NAME
from kst.api import ApiConfig
from kst.cli.common import (
    ActionResponse,
    ActionType,
    ForceMode,
    OperationType,
    PreparedAction,
    ResultType,
    SyncResults,
)
from kst.console import OutputConsole, OutputFormat, render_plain_text
from kst.diff import ChangesDict, ChangeType, three_way_diff
from kst.exceptions import InvalidRepositoryError, InvalidRepositoryMemberError
from kst.git import locate_root
from kst.repository import ACCEPTED_INFO_EXTENSIONS, MemberBase, Repository, RepositoryDirectory
from kst.utils import yaml

console = OutputConsole(logging.getLogger(__name__))


# --- Utility functions ---
def api_config_prompt(tenant_url: str | None, api_token: str | None, interactive: bool = True) -> ApiConfig:
    """Prompt the user for missing API configuration values unless interactive is False.

    The function will prompt the user for the tenant_url and api_token if they are not
    provided as arguments. In the event that the function cannot return a valid ApiConfig
    it will raise a typer. Exit exception with a status code of 2.

    Args:
        tenant_url (str | None): The Kandji Tenant URL.
        api_token (str | None): The Kandji API Token.
        interactive (bool): Whether to prompt the user for missing values.

    Returns:
        ApiConfig: A validated ApiConfig object.

    Raises:
        typer.BadParameter: If the function cannot return a valid ApiConfig object.

    """

    if interactive and tenant_url is None:
        console.debug("Tenant URL not provided. Prompting for input.")
        tenant_url = typer.prompt("Enter Kandji Tenant API URL")
    if interactive and api_token is None:
        console.debug("API Token not provided. Prompting for input.")
        api_token = typer.prompt("Enter API Token", hide_input=True)

    if tenant_url is None:
        msg = "You must provide a valid Kandji Tenant API URL. Use the --tenant-url flag or the set the KST_TENANT environment variable."
        console.error(msg)
        raise typer.BadParameter(msg)
    if api_token is None:
        msg = "You must provide a valid Kandji API Token. Use the --api-token flag or the set the KST_TOKEN environment variable."
        console.error(msg)
        raise typer.BadParameter(msg)

    try:
        console.debug(f"Creating ApiConfig with tenant_url: {tenant_url}")
        config = ApiConfig(tenant_url=tenant_url, api_token=api_token)
    except ValidationError as error:
        msg = "\n* " + "\n* ".join([error["msg"].removeprefix("Value error,").strip() for error in error.errors()])
        console.error(msg)
        raise typer.BadParameter(msg)

    # Ensure the URL is a valid Kandji tenant API URL
    console.debug(f"Validating URL: {config.url}")
    response = requests.get(urljoin(config.url, "/app/v1/ping"), params={"source": "kst"})
    if not response.ok:
        msg = f"Unable to connect to ({config.url}). Please check the URL then try again."
        console.error(msg)
        raise typer.BadParameter(msg)

    console.debug(f"Response content: {response.text}")
    console.debug(f"Response status code: {response.status_code}")

    return config


def delete_member_directory(member: MemberBase):
    """Delete a member directory from the local repository.

    Args:
        member: The repository member to delete.

    """
    if member.info_path.parent.exists():
        console.debug(f"Deleting directory for {member.id} at {member.info_path.parent}")
        shutil.rmtree(member.info_path.parent)
        if member.info_path.parent.exists():
            console.print_error(
                f"The directory for {member.id} was not deleted. Please cleanup manually ({member.info_path.parent})."
            )
        else:
            console.debug(f"Directory for {member.id} deleted successfully.")
            for child in member.children:
                child.path = None
    else:
        console.print_warning(
            f"The directory for {member.id} was not found on disk at {member.info_path.parent}. It may have already been deleted."
        )


def filter_changes[MemberType: MemberBase](
    local_repo: Repository[MemberType], remote_repo: Repository[MemberType]
) -> ChangesDict:
    """Compare two repositories and return the changes between them.

    Args:
        local_repo (Repository): The local repository.
        remote_repo (Repository): The remote repository.

    Returns:
        ChangesDict: A dictionary of changes between the repositories.

    """
    changes: ChangesDict[MemberType] = {
        ChangeType.NONE: [],
        ChangeType.CREATE_REMOTE: [],
        ChangeType.UPDATE_REMOTE: [],
        ChangeType.CREATE_LOCAL: [],
        ChangeType.UPDATE_LOCAL: [],
        ChangeType.CONFLICT: [],
    }
    all_ids = set(local_repo.keys()) | set(remote_repo.keys())
    for member_id in all_ids:
        local_member = local_repo.get(member_id)
        remote_member = remote_repo.get(member_id)

        base_hash = local_member.sync_hash if local_member is not None else None
        local_hash = local_member.diff_hash if local_member is not None else None
        remote_hash = remote_member.diff_hash if remote_member is not None else None

        change_type = three_way_diff(
            base=base_hash,
            local=local_hash,
            remote=remote_hash,
        )
        console.debug(f"Change type for {member_id}: {change_type}")

        changes[change_type].append((local_member, remote_member))
    return changes


def is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    with contextlib.suppress(ValueError):
        UUID(value, version=4)
        console.debug(f"Value {value} is a valid UUID.")
        return True
    console.debug(f"Value {value} is not a valid UUID.")
    return False


def update_local_member[MemberType: MemberBase](
    local_repo: Repository[MemberType], result: ActionResponse[MemberType]
) -> None:
    """Update local repository with the api response from the sync operation.

    Args:
        local_repo (Repository): The local repository object.
        result (ActionResponse): The results of the sync operation.

    """
    if local_repo.root is None:
        raise ValueError("The local_repo must have a root path set. Got None.")

    if result.member is None:
        raise ValueError(f"The result's member attribute must not be None (got {result}).")

    if result.id not in local_repo:
        raise ValueError(f"The result's ID must be in the local repository (got {result.id}).")

    # Make a local copy updated with the API response data
    local_member = local_repo[result.id].updated(result.member)

    # If the ID has changed delete the old ID before adding the updated ID
    if result.id != result.member.id:
        del local_repo[result.id]

    # Update the sync hash with the current diff hash and write the repository member to disk
    local_member.sync_hash = local_member.diff_hash
    local_member.ensure_paths(local_repo.root)
    local_member.write()

    # Add the updated member to the local repository
    local_repo[result.member.id] = local_member


def validate_output_path(*, directory: RepositoryDirectory, override: str | None = None) -> Path:
    """Return the output path for the new repository member.

    If an override path is provided, it will be used. Otherwise, the repository at the current
    working directory will be used.

    If an invalid override path is provided or fallback to the current directory fails, an exception will be raised.

    Args:
        override_path (Path | None): The path to override the output path.

    Returns:
        Path: The output path.

    Raises:
        typer.BadParameter: If the output path cannot be determined

    """

    # If an override path is provided, check that it is a valid path in a kst repository
    if override is not None:
        override_path = Path(override).expanduser().resolve()
        console.debug(f"Output path provided: {override_path}")
        try:
            member_root = git.locate_root(cd_path=override_path) / directory
            if not override_path.is_relative_to(member_root):
                raise InvalidRepositoryError
        except InvalidRepositoryError:
            msg = f"The output path must be located inside a {directory} directory of a valid kst repository."
            console.error(msg)
            raise typer.BadParameter(msg)
        return override_path.resolve()

    # If override_path is not provided assume cwd is the destination repository
    try:
        console.debug("No output path provided. Using current working directory.")
        return git.locate_root() / directory
    except InvalidRepositoryError:
        msg = (
            "An output path was not specified and the current directory has not been initialized as a Kandji Sync Toolkit "
            "repository. To specify an output path use the -o/--output option and a path inside a valid "
            "repository."
        )
        console.error(msg)
        raise typer.BadParameter(msg)


def validate_repo_path(
    repo: Path | str = ".", subdir: RepositoryDirectory | None = None, validate_subdir: bool = False
) -> Path:
    """Validate and return a valid kst repository path."""

    repo_path = Path(repo).expanduser().resolve()
    try:
        root = locate_root(cd_path=repo_path)
        if subdir is not None:
            if validate_subdir and not repo_path.is_relative_to(root / subdir):
                raise InvalidRepositoryError
            (root / subdir).mkdir(parents=True, exist_ok=True)
            return root / subdir
        return root
    except InvalidRepositoryError:
        subdir_name = subdir + " " if subdir is not None and validate_subdir else ""
        msg = f"The path provided for --repo option is not a valid kst {subdir_name}directory. (got {repo_path})"
        console.error(msg)
        raise typer.BadParameter(msg)


def verify_all_ids_found[MemberType: MemberBase](
    member_ids: Iterable[str],
    local_repo: Repository[MemberType],
    remote_repo: Repository[MemberType],
    local_only=False,
    remote_only=False,
) -> None:
    """Verify that all member IDs are found in either the local or remote repository.

    Args:
        member_ids (Iterable[str]): The IDs of the members to verify.
        local_repo (Repository): The local repository to check.
        remote_repo (Repository): The remote repository to check.

    Raises:
        typer.BadParameter: If a member ID is not found in the local or remote repositories.

    """
    errors = []
    for member_id in member_ids:
        if member_id not in local_repo and member_id not in remote_repo:
            location = "local" if local_only else "remote" if remote_only else "local or remote"
            errors.append(f"Repository member with ID {member_id} not found in {location} repository.")

    if errors:
        console.error("\n".join(errors))
        raise typer.BadParameter("\n".join(errors))


# --- Load / Fetch Functions ---
def load_members_by_id[MemberType: MemberBase](
    repo_path: Path, member_type: type[MemberType], member_ids: Iterable[str], raise_on_missing=True
) -> Iterator[MemberType]:
    """Load repository members by their IDs.

    Args:
        repo_path: The path to the repository.
        member_type: The repository member class.
        member_ids: The IDs of the members to load.
        raise_on_missing: Raise an error if a member ID is not found.

    Yields:
        The repository members with the given IDs.

    Raises:
        typer.Exit: If the given ID is not found and raise_on_missing is True.
        typer.BadParameter: If the given ID is not found and raise_on_missing is True.

    """
    if not member_ids:
        return

    try:
        repo = Repository.load_path(model=member_type, path=repo_path)
        console.debug(f"Loaded repository at {repo.root}")
    except InvalidRepositoryError as error:
        console.print_error(f"An error occurred while loading the repository: {error}")
        raise typer.Exit(code=1)
    except InvalidRepositoryMemberError as error:
        console.print_error(f"An error occurred while loading a repository member: {error}")
        raise typer.Exit(code=1)

    for member_id in member_ids:
        try:
            console.debug(f"Retrieving member with ID {member_id} from local repository.")
            yield repo[member_id]
        except KeyError:
            if not raise_on_missing:
                console.debug(f"Skipping missing member with ID {member_id}")
                continue
            msg = f"Member with ID {member_id} not found in local repository at {repo_path.resolve()}."
            console.error(msg)
            raise typer.BadParameter(msg)


def load_members_by_path[MemberType: MemberBase](
    member_type: type[MemberType], member_paths: Iterable[Path], raise_on_missing=True
) -> Iterator[MemberType]:
    """Load repository members from a list of paths.

    Args:
        member_type (type[RepositoryMemberType]): The type of the repository member.
        member_paths (Iterable[Path]): The paths to the repository members.
        raise_on_missing (bool): Raise an error if a member path is not found.

    Yields:
        Repository members loaded from the given paths.

    Raises:
        typer.Exit: If a repository member cannot be loaded from a given path.
        typer.BadParameter: If a given path does not exist and raise_on_missing is True.

    """
    if not member_paths:
        return

    for member_path in member_paths:
        # Throw error if trying to load the wrong type from a path.
        validate_repo_path(repo=member_path, subdir=RepositoryDirectory.from_type(member_type), validate_subdir=True)

    path_set = set()
    for path in member_paths:
        console.debug(f"Loading member from path: {path}")
        if not path.exists():
            if not raise_on_missing:
                console.debug(f"Skipping missing path {path}")
                continue
            msg = f"Path {path} does not exist."
            console.error(msg)
            raise typer.BadParameter(msg)
        if path.is_dir():
            console.debug(f"Path {path} is a directory. Loading recursively.")
            yield from load_members_by_path(
                member_type=member_type,
                member_paths=[p for p in path.rglob("info.*") if p.suffix in ACCEPTED_INFO_EXTENSIONS],
            )
        else:
            if path in path_set:
                console.debug(f"Skipping duplicate path {path}")
                continue
            try:
                yield member_type.from_path(path)
            except InvalidRepositoryMemberError as error:
                console.print_error(f"An error occurred while loading {path}: {error}")
                raise typer.Exit(code=1)


def get_local_members[MemberType: MemberBase](
    repo: Path,
    member_type: type[MemberType],
    *,
    member_paths: Iterable[Path] = [],
    member_ids: Iterable[str] = [],
    all_members: bool = False,
    raise_on_missing_id: bool = True,
    raise_on_missing_path: bool = True,
) -> Repository[MemberType]:
    """Get a filtered and de-duplicated local repository object.

    Args:
        repo (Path): The path to the repository.
        member_paths (Iterable[Path]): The paths to the repository members to include.
        member_ids (Iterable[str]): The IDs of the repository members to include.
        all_members (bool): Include all members. If True, paths and member_ids are ignored.
        raise_on_missing_id (bool): Raise an error if a member ID is not found.
        raise_on_missing_path (bool): Raise an error if a member path is not found.

    Returns:
        The generated repository mapping.

    Raises:
        typer.Exit: If selected repository members cannot be loaded.
        typer.BadParameter: If not all members are found in the repository.

    """

    member_id_set = set(member_ids)

    if all_members:
        try:
            console.debug(f"Loading all members from the repository at {repo}")
            return Repository.load_path(model=member_type, path=repo)
        except InvalidRepositoryError as error:
            console.print_error(f"An error occurred while loading the repository: {error}")
            raise typer.Exit(code=1)
        except InvalidRepositoryMemberError as error:
            console.print_error(f"An error occurred while loading a repository member: {error}")
            raise typer.Exit(code=1)

    # Gather list of items to push and remove duplicates
    members = list(
        load_members_by_id(
            repo_path=repo, member_type=member_type, member_ids=member_id_set, raise_on_missing=raise_on_missing_id
        )
    )
    members.extend(
        member
        for member in load_members_by_path(
            member_type=member_type, member_paths=set(member_paths), raise_on_missing=raise_on_missing_path
        )
        if member.id not in member_id_set
    )
    console.debug(f"Loaded {len(members)} members from the repository at {repo}")

    if not all(member.info_path.parent.is_relative_to(repo.resolve()) for member in members):
        msg = f"All repository members must be within the repository at {repo}."
        console.error(msg)
        raise typer.BadParameter(msg)

    try:
        console.debug("Generating repository mapping for loaded local members.")
        return Repository(members, root=repo)
    except InvalidRepositoryError as error:
        console.print_error(f"An error occurred while loading the repository: {error}")
        raise typer.Exit(code=1)


def get_remote_members[MemberType: MemberBase](
    config: ApiConfig,
    member_type: type[MemberType],
    *,
    member_ids: Iterable[str] = [],
    all_members: bool = False,
    raise_on_missing: bool = True,
) -> Repository[MemberType]:
    """Get a filtered object of remote repository members.

    Args:
        config (ApiConfig): The API configuration.
        member_type (RepositoryMemberType): The type of members to fetch.
        member_ids (Iterable[str]): The IDs of the members to include.
        all_members (bool): Include all members. If True, member_ids is ignored.
        raise_on_missing (bool): Raise an error if a repository member is not found.

    Returns:
        The generated repository mapping.

    Raises:
        typer.Exit: If an error occurs while fetching members.
        typer.BadParameter: If not all members are found in the repository.

    """

    try:
        console.debug(f"Fetching members from the remote API at {config.url}")
        members = member_type.list_remote(config=config).results
        console.debug(f"Fetched {len(members)} members")
    except (requests.ConnectionError, requests.HTTPError, ValidationError) as error:
        console.print_error(f"An error occurred while fetching: {error}")
        raise typer.Exit(code=1)

    if not all_members:
        console.debug(f"Filtering members to requested IDs: {member_ids}")
        members = [member for member in members if member.id in member_ids]

    missing_ids = set(member_ids) - {member.id for member in members}
    for member_id in missing_ids:
        console.debug(f"Member with ID {member_id} not found in Kandji.")

    if raise_on_missing and missing_ids:
        msg = "Requested members not found in Kandji:"
        for member_id in missing_ids:
            msg += f"\n* {member_id}"
        console.error(msg)
        raise typer.BadParameter(msg)

    console.debug("Generating repository mapping for fetched remote members.")
    return Repository[member_type](member_type.from_api_payload(member) for member in members)


def get_member[MemberType: MemberBase](
    config: ApiConfig | None, member_type: type[MemberType], key: str, repo: str, remote: bool
) -> MemberType:
    """Get a repository member by ID or path from a local repo or remote API

    Args:
        config: The API configuration to use if fetching from remote.
        repo: The path to the local repository.
        key: The ID or path to search.
        remote: If True, search the remote repo. Otherwise, search the local repo.

    Returns:
        The repository member object.

    Raises:
        typer.BadParameter: If the input is not a valid ID or path.

    """
    if is_uuid(key):
        console.debug(f"Key {key} identified as ID. Loading from ID.")
        if remote:
            member_id = key
        else:
            return next(
                load_members_by_id(
                    repo_path=validate_repo_path(repo=repo, subdir=RepositoryDirectory.from_type(member_type)),
                    member_type=member_type,
                    member_ids=[key],
                )
            )
    elif Path(key).exists():
        console.debug(f"Key {key} identified as path. Loading from path.")
        discovered_members = list(load_members_by_path(member_type=member_type, member_paths=[Path(key)]))
        if len(discovered_members) == 1:
            if remote:
                member_id = discovered_members[0].id
            else:
                return discovered_members[0]
        elif len(discovered_members) == 0:
            msg = f"Found no items at path {key}. Please check the path and try again."
            console.error(msg)
            raise typer.BadParameter(msg)
        else:
            msg = f"Found {len(discovered_members)} items at path {Path(key).expanduser().resolve()}."
            for member in discovered_members:
                msg += f"\n* {member.id}"
            msg += "\nPlease specify an ID or direct path."
            console.error(msg)
            raise typer.BadParameter(msg)
    else:
        msg = f"{key} is not a valid ID or existing path. Please double-check the lookup value."
        console.error(msg)
        raise typer.BadParameter(msg)

    # config is guaranteed to be non-None if remote is True
    return next(
        iter(
            get_remote_members(
                config=config,  # type: ignore[reportArgumentType]
                member_type=member_type,
                member_ids=[member_id],
                raise_on_missing=True,
            ).values()
        )
    )


# --- Prepare Action Functions ---
def prepare_pull_actions[MemberType: MemberBase](
    changes: ChangesDict[MemberType], force_pull: bool = False, allow_delete: bool = False
) -> list[PreparedAction[MemberType]]:
    """Prepare an iterable of actionable items from the changes dictionary.

    Args:
        changes (ChangesDict): The changes dictionary to prepare actions from.
        force_pull (bool): Whether to force pull changes in case of conflicts.
        allow_delete (bool): Whether to allow deletion.

    Returns:
        list[PreparedAction]: A list of actions to take for each repository member.

    """
    actions = []
    for change_type, members in changes.items():
        match change_type:
            case ChangeType.CREATE_REMOTE:
                actions.extend(
                    PreparedAction(
                        action=ActionType.CREATE, operation=OperationType.PULL, change=change_type, member=remote
                    )
                    for _, remote in members
                    if remote is not None
                )
            case ChangeType.UPDATE_REMOTE:
                actions.extend(
                    PreparedAction(
                        action=ActionType.UPDATE, operation=OperationType.PULL, change=change_type, member=remote
                    )
                    for _, remote in members
                    if remote is not None
                )
            case ChangeType.CONFLICT | ChangeType.UPDATE_LOCAL:
                if force_pull:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.UPDATE, operation=OperationType.PULL, change=change_type, member=remote
                        )
                        for _, remote in members
                        if remote is not None
                    )
                else:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.SKIP, operation=OperationType.SKIP, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
            case ChangeType.CREATE_LOCAL:
                if allow_delete:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.DELETE, operation=OperationType.PULL, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
                else:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.SKIP, operation=OperationType.SKIP, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
    return actions


def prepare_push_actions[MemberType: MemberBase](
    changes: ChangesDict[MemberType], force_push: bool = False, allow_delete: bool = False
) -> list[PreparedAction[MemberType]]:
    """Prepare an iterable of actionable items from the changes dictionary.

    Args:
        changes (ChangesDict): The changes dictionary to prepare actions from.
        force_push (bool): Whether to force push changes in case of conflicts.
        allow_delete (bool): Whether to allow deletion of members.

    Returns:
        list[PreparedAction]: A list of actions to take for each repository member.

    """
    actions: list[PreparedAction[MemberType]] = []
    for change_type, members in changes.items():
        match change_type:
            case ChangeType.CREATE_LOCAL:
                actions.extend(
                    PreparedAction(
                        action=ActionType.CREATE, operation=OperationType.PUSH, change=change_type, member=local
                    )
                    for local, _ in members
                    if local is not None
                )
            case ChangeType.UPDATE_LOCAL:
                actions.extend(
                    PreparedAction(
                        action=ActionType.UPDATE, operation=OperationType.PUSH, change=change_type, member=local
                    )
                    for local, _ in members
                    if local is not None
                )
            case ChangeType.CONFLICT | ChangeType.UPDATE_REMOTE:
                if force_push:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.UPDATE, operation=OperationType.PUSH, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
                else:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.SKIP, operation=OperationType.SKIP, change=change_type, member=remote
                        )
                        for _, remote in members
                        if remote is not None
                    )
            case ChangeType.CREATE_REMOTE:
                if allow_delete:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.DELETE, operation=OperationType.PUSH, change=change_type, member=remote
                        )
                        for _, remote in members
                        if remote is not None
                    )
                else:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.SKIP, operation=OperationType.SKIP, change=change_type, member=remote
                        )
                        for _, remote in members
                        if remote is not None
                    )
    return actions


def prepare_delete_actions[MemberType: MemberBase](
    local_repo: Repository[MemberType],
    remote_repo: Repository[MemberType],
    member_ids: Iterable[str],
    local_only: bool,
    remote_only: bool,
) -> list[PreparedAction[MemberType]]:
    """Prepare delete actions for repository members."""
    actions: list[PreparedAction] = []
    for member_id in member_ids:
        if not local_only:
            remote_member = remote_repo.get(member_id)
            if remote_member is not None:
                actions.append(
                    PreparedAction(
                        action=ActionType.DELETE,
                        operation=OperationType.PUSH,  # Push to signify remote deletion
                        change=ChangeType.CREATE_REMOTE,  # Create remote to signify missing remote member
                        member=remote_member,
                    )
                )
        if not remote_only:
            local_member = local_repo.get(member_id)
            if local_member is not None:
                actions.append(
                    PreparedAction(
                        action=ActionType.DELETE,
                        operation=OperationType.PULL,  # Pull to signify local deletion
                        change=ChangeType.CREATE_LOCAL,  # Create local to signify missing local member
                        member=local_member,
                    )
                )
    return actions


def prepare_sync_actions[MemberType: MemberBase](
    changes: ChangesDict[MemberType], force_mode: ForceMode
) -> list[PreparedAction[MemberType]]:
    """Prepare actions for syncing to Kandji.

    Args:
        changes: A dictionary of changes between local and remote repository members.
        force_mode: The force mode to use when resolving conflicts.

    Returns:
        A list of prepared actions to be taken to sync to Kandji.
    """
    actions: list[PreparedAction[MemberType]] = []
    for change_type, members in changes.items():
        match change_type:
            case ChangeType.CREATE_LOCAL:
                actions.extend(
                    PreparedAction(
                        action=ActionType.CREATE, operation=OperationType.PUSH, change=change_type, member=local
                    )
                    for local, _ in members
                    if local is not None
                )
            case ChangeType.UPDATE_LOCAL:
                actions.extend(
                    PreparedAction(
                        action=ActionType.UPDATE, operation=OperationType.PUSH, change=change_type, member=local
                    )
                    for local, _ in members
                    if local is not None
                )
            case ChangeType.CREATE_REMOTE:
                actions.extend(
                    PreparedAction(
                        action=ActionType.CREATE, operation=OperationType.PULL, change=change_type, member=remote
                    )
                    for _, remote in members
                    if remote is not None
                )
            case ChangeType.UPDATE_REMOTE:
                actions.extend(
                    PreparedAction(
                        action=ActionType.UPDATE, operation=OperationType.PULL, change=change_type, member=remote
                    )
                    for _, remote in members
                    if remote is not None
                )
            case ChangeType.CONFLICT:
                if force_mode == ForceMode.PUSH:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.UPDATE, operation=OperationType.PUSH, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
                elif force_mode == ForceMode.PULL:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.UPDATE, operation=OperationType.PULL, change=change_type, member=remote
                        )
                        for _, remote in members
                        if remote is not None
                    )
                else:
                    actions.extend(
                        PreparedAction(
                            action=ActionType.SKIP, operation=OperationType.SKIP, change=change_type, member=local
                        )
                        for local, _ in members
                        if local is not None
                    )
    return actions


# --- Do Action Functions ---
def do_push[MemberType: MemberBase](
    config: ApiConfig, local_repo: Repository[MemberType], action: PreparedAction[MemberType]
) -> ActionResponse[MemberType]:
    if action.operation not in {OperationType.PUSH, OperationType.SKIP}:
        raise ValueError("The action must be a push operation.")

    try:
        match action.action:
            case ActionType.CREATE:
                result = action.member.create_remote(config=config)
            case ActionType.UPDATE:
                result = action.member.update_remote(config=config)
            case ActionType.DELETE:
                result = action.member.delete_remote(config=config)
            case ActionType.SKIP:
                result = None
    except (requests.HTTPError, requests.ConnectionError, ValueError) as e:
        console.print_error(f"Failed to {action.action} item in Kandji {action.member.id}. {e}", stderr=False)
        return ActionResponse(
            id=action.member.id,
            action=action.action,
            operation=action.operation,
            result=ResultType.FAILURE,
            member=action.member,
        )

    if action.action is ActionType.SKIP:
        skip_reason = "conflicting changes" if action.change is ChangeType.CONFLICT else "remote only changes"
        console.print_warning(f"{action.member.name} ({action.member.id}) skipped due to {skip_reason}", stderr=False)

        action_response = ActionResponse(
            id=action.member.id,
            action=action.action,
            operation=action.operation,
            result=ResultType.SKIPPED,
            member=action.member,
        )
    else:
        msg = f"{action.member.name} ({action.member.id}) {action.action.past_tense()} in Kandji successfully"
        if result is not None and action.member.id != result.id:
            # Newly created items will have a different ID
            msg += f" with new Kandji ID: {result.id}"
        console.print_success(msg)

        action_response = ActionResponse(
            id=action.member.id,
            action=action.action,
            operation=action.operation,
            result=ResultType.SUCCESS,
            member=action.member.from_api_payload(result) if result is not None else None,
        )

        # Most API requests return an updated version so update the local repository with the API response
        if action.action is not ActionType.DELETE:
            update_local_member(local_repo, action_response)

    return action_response


def do_pushes[MemberType: MemberBase](
    config: ApiConfig, local_repo: Repository[MemberType], actions: Iterable[PreparedAction[MemberType]]
) -> SyncResults[MemberType]:
    """Push the changes defined by the actions tuples to Kandji.

    Args:
        config (ApiConfig): The API configuration to use for the push.
        actions (Iterable[PreparedAction]): The actions to take.

    Returns:
        SyncResults: A dataclass containing the successful and failed actions.

    """
    push_results = SyncResults[MemberType]()
    if not actions:
        console.print("Nothing to do.")
        return push_results

    for action in track(
        actions,
        description="Pushing changes to Kandji",
        console=console.stdout,
        transient=True,
        disable=console.logs_to_std,
    ):
        result = do_push(config=config, local_repo=local_repo, action=action)
        match result.result:
            case ResultType.SUCCESS:
                push_results.success.append(result)
            case ResultType.FAILURE:
                push_results.failure.append(result)
            case ResultType.SKIPPED:
                push_results.skipped.append(result)

    return push_results


def do_pull[MemberType: MemberBase](
    local_repo: Repository[MemberType], action: PreparedAction[MemberType]
) -> ActionResponse[MemberType]:
    if action.operation not in {OperationType.PULL, OperationType.SKIP}:
        raise ValueError("The action must be a pull operation.")

    if local_repo.root is None:
        raise ValueError("The local_repo must have a root path set.")

    match action.action:
        case ActionType.CREATE | ActionType.UPDATE:
            if action.member is not None and action.member.id in local_repo:
                # Make a local copy updated with the API response data
                local_member = local_repo[action.member.id].updated(action.member)
            else:
                local_member = action.member
            local_member.sync_hash = local_member.diff_hash
            local_member.ensure_paths(repo_path=local_repo.root)
            local_member.write()
            local_repo[action.member.id] = local_member
        case ActionType.DELETE:
            local_member = local_repo.pop(action.member.id)
            delete_member_directory(local_member)
            local_member = None
        case ActionType.SKIP:
            local_member = action.member

    if action.action is ActionType.SKIP:
        skip_reason = "conflicting changes" if action.change is ChangeType.CONFLICT else "local only changes"
        console.print_warning(f"{action.member.name} ({action.member.id}) skipped due to {skip_reason}", stderr=False)
        result_type = ResultType.SKIPPED
    else:
        console.print_success(
            f"{action.member.name} ({action.member.id}) {action.action.past_tense()} in local repo successfully"
        )
        result_type = ResultType.SUCCESS

    return ActionResponse(
        id=action.member.id,
        action=action.action,
        operation=action.operation,
        result=result_type,
        member=local_member,
    )


def do_pulls[MemberType: MemberBase](
    local_repo: Repository[MemberType], actions: list[PreparedAction[MemberType]]
) -> SyncResults:
    """Pull the changes defined by the actions tuples from Kandji."""

    pull_results = SyncResults()
    if not actions:
        console.print("Nothing to do.")
        return pull_results

    if local_repo.root is None:
        raise ValueError("The local_repo must have a root path set.")

    for action in track(
        actions,
        description="Pulling changes from Kandji",
        console=console.stdout,
        transient=True,
        disable=console.logs_to_std,
    ):
        result = do_pull(local_repo=local_repo, action=action)
        match result.result:
            case ResultType.SUCCESS:
                pull_results.success.append(result)
            case ResultType.FAILURE:
                pull_results.failure.append(result)
            case ResultType.SKIPPED:
                pull_results.skipped.append(result)

    return pull_results


def do_sync[MemberType: MemberBase](
    config: ApiConfig,
    local_repo: Repository[MemberType],
    actions: list[PreparedAction[MemberType]],
    description: str = "Syncing changes with Kandji",
) -> SyncResults[MemberType]:
    """Sync local repository with Kandji.

    Args:
        config: The API configuration to use for syncing.
        local_repo: The local repository.
        actions: A list of prepared actions to take to sync.

    Returns:
        SyncResults: A dataclass containing the successful and failed actions.
    """
    results = SyncResults[MemberType]()

    for action in track(
        actions,
        description=description,
        console=console.stdout,
        transient=True,
        disable=console.logs_to_std,
    ):
        match action.operation:
            case OperationType.PUSH:
                result = do_push(config=config, local_repo=local_repo, action=action)
            case OperationType.PULL:
                result = do_pull(local_repo=local_repo, action=action)
            case OperationType.SKIP:
                console.print_warning(
                    f"{action.member.name} ({action.member.id}) skipped due to conflicting changes", stderr=False
                )
                result = ActionResponse(
                    id=action.member.id,
                    action=action.action,
                    operation=action.operation,
                    result=ResultType.SKIPPED,
                    member=action.member,
                )

        match result.result:
            case ResultType.SUCCESS:
                results.success.append(result)
            case ResultType.FAILURE:
                results.failure.append(result)
            case ResultType.SKIPPED:
                results.skipped.append(result)

    return results


# --- Display Report Functions ---


def format_list_table[MemberType: MemberBase](
    changes: ChangesDict[MemberType], local_only: bool, remote_only: bool
) -> Table:
    rows: list[dict[str, str]] = []
    for change_type in changes:
        for local, remote in changes[change_type]:
            row = OrderedDict[str, str]()
            if local and remote and local.name != remote.name:
                row["id"] = local.id
                row["name"] = f"[yellow]{local.name} / {remote.name}[/]"
            elif local:
                row["id"] = local.id
                row["name"] = local.name
            elif remote:
                row["id"] = remote.id
                row["name"] = remote.name
            else:
                raise ValueError("Both local and remote are None")

            if local_only is remote_only is False:
                match change_type:
                    case ChangeType.NONE:
                        row["status"] = "[green]No Pending Changes[/]"
                    case ChangeType.CREATE_REMOTE:
                        row["status"] = "[yellow]New Remote Item[/]"
                    case ChangeType.UPDATE_REMOTE:
                        row["status"] = "[yellow]Updated Remote Item[/]"
                    case ChangeType.CREATE_LOCAL:
                        row["status"] = "[yellow]New Local Item[/]"
                    case ChangeType.UPDATE_LOCAL:
                        row["status"] = "[yellow]Updated Local Item[/]"
                    case ChangeType.CONFLICT:
                        row["status"] = "[red]Conflicting Changes[/]"
            rows.append(row)

    table_width = min(max(console.width - 1, 78), 120)
    table = Table(box=box.SIMPLE, width=table_width)

    # Add Headers
    table.add_column("ID", style="bold italic", width=36)
    table.add_column(
        "Name (Local/Remote)" if any(" / " in row["name"] for row in rows) else "Name", overflow="fold", ratio=1
    )
    if local_only is remote_only is False:
        table.add_column("Status", overflow="fold", ratio=1)

    # Add Rows
    for row in rows:
        table.add_row(*row.values())

    return table


def format_plain_text_list[MemberType: MemberBase](
    changes: ChangesDict[MemberType], format: OutputFormat, local_only: bool, remote_only: bool
) -> str:
    """Format the output for the list command as either a human readable table or a machine readable format."""
    rows = []
    for change_type in changes:
        for local, remote in changes[change_type]:
            if local is not None:
                row = {"id": local.id}
            elif remote is not None:
                row = {"id": remote.id}
            else:
                raise ValueError("Both local and remote are None")
            row |= {
                "local": None if local is None else local.prepare_syntax_dict(syntax=format.to_syntax()),
                "remote": None if remote is None else remote.prepare_syntax_dict(syntax=format.to_syntax()),
            }
            if local_only is remote_only is False:
                row["status"] = str(change_type)
            if format is OutputFormat.PLIST:
                # plistlib does not support None values
                row = {k: v for k, v in row.items() if v is not None}
            rows.append(row)

    match format:
        case OutputFormat.PLIST:
            return plistlib.dumps(rows, fmt=plistlib.FMT_XML, sort_keys=False).decode()
        case OutputFormat.JSON:
            return json.dumps(rows, indent=2)
        case OutputFormat.YAML:
            output_str = io.StringIO()
            yaml.dump(rows, output_str)
            return output_str.getvalue()
        case _:
            return render_plain_text(
                format_list_table(changes=changes, local_only=local_only, remote_only=remote_only), new_line_start=True
            )


def show_pull_report[MemberType: MemberBase](
    pull_results: SyncResults[MemberType], changes: ChangesDict[MemberType], force_pull: bool, allow_delete: bool
) -> None:
    """Show a summary of the pull operation results.

    Args:
        pull_results: The results of the pull operation.
        changes: The changes dictionary used to generate the pull results.
        force_pull: Whether the pull operation was forced.
        allow_delete: Whether the pull operation was allowed to delete members.

    """
    update_table = Table(title="Updated Item Summary", title_justify="left", box=box.SIMPLE)
    update_table.add_column("Action", width=12)
    update_table.add_column("Success", width=8)
    update_table.add_column("Failure", width=8)

    success_counter = Counter(result.action for result in pull_results.success)
    failure_counter = Counter(result.action for result in pull_results.failure)

    if success_counter[ActionType.CREATE] > 0 or failure_counter[ActionType.CREATE] > 0:
        update_table.add_row(
            "Created", str(success_counter[ActionType.CREATE]), str(failure_counter[ActionType.CREATE])
        )
    if success_counter[ActionType.UPDATE] > 0 or failure_counter[ActionType.UPDATE] > 0:
        update_table.add_row(
            "Updated", str(success_counter[ActionType.UPDATE]), str(failure_counter[ActionType.UPDATE])
        )
    if success_counter[ActionType.DELETE] > 0 or failure_counter[ActionType.DELETE] > 0:
        update_table.add_row(
            "Deleted", str(success_counter[ActionType.DELETE]), str(failure_counter[ActionType.DELETE])
        )

    if update_table.row_count > 0:
        console.print(update_table, new_line_start=True)

    skip_table = Table(title="Skipped Item Summary", title_justify="left", box=box.SIMPLE)
    skip_table.add_column("Reason", width=23)
    skip_table.add_column("Count", width=8)

    if len(changes[ChangeType.NONE]) > 0:
        skip_table.add_row("Already up to date", str(len(changes[ChangeType.NONE])))
    if not allow_delete and len(changes[ChangeType.CREATE_LOCAL]) > 0:
        skip_table.add_row("Local only item", str(len(changes[ChangeType.CREATE_LOCAL])))
    if not force_pull and len(changes[ChangeType.UPDATE_LOCAL]) > 0:
        skip_table.add_row("Local only updates", str(len(changes[ChangeType.UPDATE_LOCAL])))
    if not force_pull and len(changes[ChangeType.CONFLICT]) > 0:
        skip_table.add_row("Conflicting changes", str(len(changes[ChangeType.CONFLICT])))

    if skip_table.row_count > 0:
        console.print(skip_table, new_line_start=True)


def show_push_report[MemberType: MemberBase](
    push_results: SyncResults[MemberType], changes: ChangesDict[MemberType], force_push: bool, allow_delete: bool
) -> None:
    """Show a summary of the push operation results.

    Args:
        push_results (SyncResults): The results of the push operation.
        changes (ChangesDict): The changes dictionary used to generate the push results.
        force_push (bool): Whether the push operation was forced.
        allow_delete (bool): Whether the push operation was allowed to delete members.

    """
    update_table = Table(title="Updated Item Summary", title_justify="left", box=box.SIMPLE)
    update_table.add_column("Action", width=12)
    update_table.add_column("Success", width=8)
    update_table.add_column("Failure", width=8)

    success_counter = Counter(result.action for result in push_results.success)
    failure_counter = Counter(result.action for result in push_results.failure)

    if success_counter[ActionType.CREATE] > 0 or failure_counter[ActionType.CREATE] > 0:
        update_table.add_row(
            "Created", str(success_counter[ActionType.CREATE]), str(failure_counter[ActionType.CREATE])
        )
    if success_counter[ActionType.UPDATE] > 0 or failure_counter[ActionType.UPDATE] > 0:
        update_table.add_row(
            "Updated", str(success_counter[ActionType.UPDATE]), str(failure_counter[ActionType.UPDATE])
        )
    if success_counter[ActionType.DELETE] > 0 or failure_counter[ActionType.DELETE] > 0:
        update_table.add_row(
            "Deleted", str(success_counter[ActionType.DELETE]), str(failure_counter[ActionType.DELETE])
        )

    if update_table.row_count > 0:
        console.print(update_table, new_line_start=True)

    skip_table = Table(title="Skipped Item Summary", title_justify="left", box=box.SIMPLE)
    skip_table.add_column("Reason", width=23)
    skip_table.add_column("Count", width=8)

    if len(changes[ChangeType.NONE]) > 0:
        skip_table.add_row("Already up to date", str(len(changes[ChangeType.NONE])))
    if not allow_delete and len(changes[ChangeType.CREATE_REMOTE]) > 0:
        skip_table.add_row("Remote only item", str(len(changes[ChangeType.CREATE_REMOTE])))
    if not force_push and len(changes[ChangeType.UPDATE_REMOTE]) > 0:
        skip_table.add_row("Remote only updates", str(len(changes[ChangeType.UPDATE_REMOTE])))
    if not force_push and len(changes[ChangeType.CONFLICT]) > 0:
        skip_table.add_row("Conflicting changes", str(len(changes[ChangeType.CONFLICT])))

    if skip_table.row_count > 0:
        console.print(skip_table, new_line_start=True)


def show_delete_report[MemberType: MemberBase](sync_results: SyncResults[MemberType]):
    """Show a summary of the delete operation."""
    deleted_table = Table(title="Deleted Item Summary", title_justify="left", box=box.SIMPLE)
    deleted_table.add_column("Location", width=12)
    deleted_table.add_column("Success", width=8)
    deleted_table.add_column("Failure", width=8)

    successes = {
        "both": set[str](),
        "local": {r.id for r in sync_results.success if r.operation is OperationType.PULL},
        "remote": {r.id for r in sync_results.success if r.operation is OperationType.PUSH},
    }
    successes["both"] |= successes["local"] & successes["remote"]
    successes["local"] -= successes["both"]
    successes["remote"] -= successes["both"]

    failures = {
        "both": set[str](),
        "local": {r.id for r in sync_results.failure if r.operation is OperationType.PULL},
        "remote": {r.id for r in sync_results.failure if r.operation is OperationType.PUSH},
    }
    failures["both"] |= failures["local"] & failures["remote"]
    failures["local"] -= failures["both"]
    failures["remote"] -= failures["both"]

    if len(successes["both"]) > 0 or len(failures["both"]) > 0:
        deleted_table.add_row(
            "Both",
            f"[green]{len(successes['both'])}",
            f"[red]{len(failures['both'])}",
        )
    if len(successes["local"]) > 0 or len(failures["local"]) > 0:
        deleted_table.add_row(
            "Local",
            f"[green]{len(successes['local'])}",
            f"[red]{len(failures['local'])}",
        )
    if len(successes["remote"]) > 0 or len(failures["remote"]) > 0:
        deleted_table.add_row(
            "Remote",
            f"[green]{len(successes['remote'])}",
            f"[red]{len(failures['remote'])}",
        )

    if deleted_table.row_count == 0:
        console.print("Nothing was selected for deletion.")
    else:
        console.print(deleted_table, new_line_start=True)


def show_sync_report[MemberType: MemberBase](
    sync_results: SyncResults[MemberType], changes: ChangesDict[MemberType], force_mode: ForceMode
):
    """Show a summary of the sync operation results.

    Args:
        sync_results (SyncResults): The results of the sync operation.
        changes (ChangesDict): The changes dictionary used to generate the sync results.
        force_mode (ForceMode): The force mode used to resolve conflicts.

    """

    # Show Push Summary if pushes were performed
    pushed_table = Table(title="Pushed Item Summary", title_justify="left", box=box.SIMPLE)
    pushed_table.add_column("Action", width=12)
    pushed_table.add_column("Success", width=8)
    pushed_table.add_column("Failure", width=8)

    push_success_counter = Counter(
        result.action for result in (r for r in sync_results.success if r.operation == OperationType.PUSH)
    )
    push_failure_counter = Counter(
        result.action for result in (r for r in sync_results.failure if r.operation == OperationType.PUSH)
    )

    if push_success_counter[ActionType.CREATE] > 0 or push_failure_counter[ActionType.CREATE] > 0:
        pushed_table.add_row(
            "Created", str(push_success_counter[ActionType.CREATE]), str(push_failure_counter[ActionType.CREATE])
        )
    if push_success_counter[ActionType.UPDATE] > 0 or push_failure_counter[ActionType.UPDATE] > 0:
        pushed_table.add_row(
            "Updated", str(push_success_counter[ActionType.UPDATE]), str(push_failure_counter[ActionType.UPDATE])
        )

    if pushed_table.row_count > 0:
        console.print(pushed_table, new_line_start=True)

    # Show Pull Summary if pulls were performed
    pulled_table = Table(title="Pulled Item Summary", title_justify="left", box=box.SIMPLE)
    pulled_table.add_column("Action", width=12)
    pulled_table.add_column("Success", width=8)
    pulled_table.add_column("Failure", width=8)

    pull_success_counter = Counter(
        result.action for result in (r for r in sync_results.success if r.operation == OperationType.PULL)
    )
    pull_failure_counter = Counter(
        result.action for result in (r for r in sync_results.failure if r.operation == OperationType.PULL)
    )
    if pull_success_counter[ActionType.CREATE] > 0 or pull_failure_counter[ActionType.CREATE] > 0:
        pulled_table.add_row(
            "Created", str(pull_success_counter[ActionType.CREATE]), str(pull_failure_counter[ActionType.CREATE])
        )
    if pull_success_counter[ActionType.UPDATE] > 0 or pull_failure_counter[ActionType.UPDATE] > 0:
        pulled_table.add_row(
            "Updated", str(pull_success_counter[ActionType.UPDATE]), str(pull_failure_counter[ActionType.UPDATE])
        )

    if pulled_table.row_count > 0:
        console.print(pulled_table, new_line_start=True)

    # Show Skipped Item Summary
    skip_table = Table(title="Skipped Item Summary", title_justify="left", box=box.SIMPLE)
    skip_table.add_column("Reason", width=23)
    skip_table.add_column("Count", width=8)

    if len(changes[ChangeType.NONE]) > 0:
        skip_table.add_row("Already up to date", str(len(changes[ChangeType.NONE])))
    if force_mode == ForceMode.SKIP and len(changes[ChangeType.CONFLICT]) > 0:
        skip_table.add_row("Conflicting changes", str(len(changes[ChangeType.CONFLICT])))

    if skip_table.row_count > 0:
        console.print(skip_table, new_line_start=True)


def save_report[MemberType: MemberBase](
    results: SyncResults[MemberType],
    report_path: Path = platformdirs.user_log_path(appname=APP_NAME) / f"{APP_NAME}_report.json",
) -> None:
    """Save the sync report to a file.

    Args:
        sync_results (SyncResults): The results of the sync operation.
        output_path (Path): The path to save the report.

    """
    if report_path.exists():
        with report_path.open("r") as file:
            try:
                sync_report = json.load(file)
                if not isinstance(sync_report, list):
                    raise json.JSONDecodeError("Invalid JSON format", "", 0)
            except json.JSONDecodeError:
                new_name = f"{report_path.name}.bkp_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
                console.warning(
                    f"The sync report file is invalid. The file will be backed up to {new_name}, and a new report file will be created."
                )
                shutil.move(
                    report_path,
                    report_path.with_name(new_name),
                )
                sync_report = []
    else:
        sync_report = []

    # Insert a new report entry
    sync_report.insert(0, results.format_report())
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as file:
        json.dump(sync_report, file, indent=2)

    console.info(f"Sync report saved to {report_path}")
