import functools
import logging
import os
import shutil
import subprocess
from collections import defaultdict
from enum import StrEnum
from pathlib import Path

from kst.console import OutputConsole
from kst.exceptions import GitRepositoryError, InvalidRepositoryError
from kst.repository import RepositoryDirectory

console = OutputConsole(logging.getLogger(__name__))


@functools.cache
def locate_git() -> str:
    """Locate the git executable.

    This function is only executed once per run and the result is cached for any
    subsequent calls.

    Returns:
        Path: The path to the git executable.

    Raises:
        FileNotFoundError: If the git executable is not found

    """

    git_path = shutil.which("git")
    if git_path is None:
        console.error("Failed to locate the git executable.")
        raise FileNotFoundError("Failed to locate the git executable.")
    try:
        # Check that the git executable is working. This may not be the case on macOS systems before CommandLineTools are installed.
        result = subprocess.run([git_path, "--version"], check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        console.error(f"git execution failed using {git_path}.")
        raise FileNotFoundError(f"Git execution yielded unexpected result: {error.stderr}") from error
    console.debug(f"Located git executable at {git_path}: {result.stdout.strip()}")
    return git_path


@functools.cache
def has_git_user_config(cd_path: Path | None = None, git_path: str | None = None) -> bool:
    """Check if the git user config is set."""

    cmd = [git_path or locate_git()]
    if cd_path:
        cmd.extend(["-C", str(cd_path)])

    try:
        subprocess.run(
            [*cmd, "config", "--get", "user.name"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(
            [*cmd, "config", "--get", "user.email"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return False
    return True


def git(
    *args: str, cd_path: Path | None = None, git_path: str | None = None, expected_exit_code=None
) -> subprocess.CompletedProcess:
    """Run a git command and return the result.

    Args:
        args (str): The arguments to pass to the git command.
        cd_path (Path): The path to run the git command from.
        git_path (str): The path to the git executable.
        expected_exit_code (int | None): The expected exit code of the command. If None, the default is 0.

    Raises:
        FileNotFoundError: If the git executable is not found.
        GitRepositoryError: If the command fails.

    """

    cmd: list[str] = [git_path or locate_git()]
    console.debug(f"Using git executable at {cmd}")

    if cd_path:
        console.debug(f"Setting CWD for git command to {cd_path}")
        cmd.extend(["-C", str(cd_path)])

    if not has_git_user_config(cd_path):
        console.debug("Git user config not set. Setting temporary user.name and user.email.")
        cmd.extend(["-c", "user.name=Kandji Sync Toolkit", "-c", "user.email=kst@kandji.invalid"])

    cmd.extend(args)
    console.debug(f"Executing git command: {' '.join(cmd)}")

    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    console.debug(f"Git command executed with exit code {result.returncode}")

    if expected_exit_code is not None and result.returncode != expected_exit_code:
        console.debug(
            f"Git command exit code ({result.returncode}) did not match expected exit code ({expected_exit_code})."
        )
        console.warning(f"Git command stdout: {result.stdout.strip()}")
        console.warning(f"Git command stderr: {result.stderr.strip()}")
        raise GitRepositoryError(f"Git command failed (exitcode {result.returncode}): {' '.join(args)}")

    console.debug(f"Git command stdout: {result.stdout.strip()}")
    console.debug(f"Git command stderr: {result.stderr.strip()}")
    return result


@functools.cache
def locate_root(*, cd_path: Path = Path("."), check_marker=True) -> Path:
    """Locate the root of the kst repository.

    The result is cached to avoid repeated calls to git for the same path.

    Args:
        cd_path (Path): The path to run the git command from.
        check_marker (bool): If True, check for the presence of a ".kst" file in the root of the repository.

    Returns:
        Path: The root of the repository.

    Raises:
        FileNotFoundError: If the git executable is not found.
        InvalidRepositoryError: If a kst repository is not found.

    """

    cd_path = cd_path.expanduser().resolve()
    console.debug(f"Received repository root search path: {cd_path}")

    # Locate an existing parent directory to search from.
    existing_dir = next((p for p in (cd_path, *cd_path.parents) if p.is_dir()), None)
    if existing_dir is None or existing_dir == Path(existing_dir.anchor):
        msg = f"Failed to locate an existing parent directory for {cd_path}"
        console.error(msg)
        raise InvalidRepositoryError(msg)

    # Locate the root of the git repository if one exists
    console.debug(f"Starting git repository search from {existing_dir}")
    try:
        result = git("rev-parse", "--show-toplevel", cd_path=existing_dir, expected_exit_code=0)
        console.debug(f"Located git repository root at {result.stdout.strip()}")
    except GitRepositoryError as error:
        msg = f"{cd_path} is not part of a valid Git repository."
        console.error(msg)
        raise InvalidRepositoryError(msg) from error

    git_root = Path(result.stdout.strip()).expanduser().resolve()
    if not check_marker:
        # If we are not checking for a marker, call off the search and return the git root
        return git_root

    # Search for a ".kst" file located in the current or any parent directory
    # Search is limited to the git root to avoid searching outside the repository
    if kst_root := next(
        (p for p in (existing_dir, *existing_dir.parents) if p.is_relative_to(git_root) and (p / ".kst").is_file()),
        None,
    ):
        console.debug(f"Located kst repository root at {kst_root}")
        return kst_root
    else:
        console.error("The git repository does not contain a .kst file. Unable to locate kst repository root.")
        raise InvalidRepositoryError(
            "The repository does not appear to be a Kandji Sync Toolkit repository. If it should be, "
            'please make sure a ".kst" file exists in the repository.'
        )


class GitStatus(StrEnum):
    """Git status enum."""

    ADDED = "Added"
    COPIED = "Copied"
    DELETED = "Deleted"
    MODIFIED = "Modified"
    RENAMED = "Renamed"
    TYPE_CHANGED = "Type changed"
    UNMERGED = "Unmerged"
    UNKNOWN = "Unknown"
    BROKEN = "Broken"

    @classmethod
    def from_status(cls, status: str) -> "GitStatus":
        """Convert a git status string to a GitStatus enum."""
        if status == "A":
            return cls.ADDED
        elif status == "C":
            return cls.COPIED
        elif status == "D":
            return cls.DELETED
        elif status == "M":
            return cls.MODIFIED
        elif status == "R":
            return cls.RENAMED
        elif status == "T":
            return cls.TYPE_CHANGED
        elif status == "U":
            return cls.UNMERGED
        else:
            return cls.UNKNOWN


StatusPath = tuple[GitStatus, Path]


def changed_paths(*, cd_path: Path = Path("."), stage: bool = False, scope: Path | None = None) -> list[StatusPath]:
    """Get a list of changed paths in the repository.

    Args:
        cd_path (Path): The path to run the git command from.
        stage (bool): If True, return staged changes.
        scope (Path | None): If provided, only return changes within this path.

    Returns:
        list[Path]: A list of changed paths.

    Raises:
        GitRepositoryError: If the command fails.

    """

    cmd = ["diff", "--name-status"]
    if stage:
        cmd.append("--staged")
    if scope is not None:
        cmd.extend(["--", str(scope)])

    result = git(*cmd, cd_path=cd_path, expected_exit_code=0)

    return [
        # git returns a list of paths relative to the cd_path. These can include "../".
        (GitStatus.from_status(status), cd_path / path)
        for status, path in (line.split(maxsplit=1) for line in result.stdout.splitlines() if line.strip())
    ]


def generate_commit_body(repo: Path, stage: bool = False) -> str:
    """Generate a commit body for kst operations."""
    changed = {
        "Profiles": defaultdict[str, set[Path]](set),
        "Scripts": defaultdict[str, set[Path]](set),
        "Other": defaultdict[str, set[Path]](set),
    }

    git_root = locate_root(cd_path=repo, check_marker=False)
    kst_root = locate_root(cd_path=repo, check_marker=True)
    commit_body = ""
    for status, path in changed_paths(cd_path=git_root, stage=stage, scope=kst_root):
        if path.is_relative_to(kst_root / RepositoryDirectory.PROFILES):
            changed["Profiles"][status].add(path)
        elif path.is_relative_to(kst_root / RepositoryDirectory.SCRIPTS):
            changed["Scripts"][status].add(path)
        else:
            changed["Other"][status].add(path)

    for key, statuses in changed.items():
        for status, paths in statuses.items():
            commit_body += f"--- {key} {status} ---\n"
            for path in sorted(paths):
                commit_body += f"* {path.relative_to(git_root)}\n"
            commit_body += "\n"

    return commit_body.strip()


def commit_all_changes(
    *, cd_path: Path = Path("."), message: str, scope: Path | None = None, include_body: bool = True, skip_git: bool = False
) -> None:
    """Add all changed files to the staging area and commit with the specified commit message.

    Args:
        cd_path (Path): The path to run the git command from.
        message (str): The commit message.
        scope (Path | None): The path to add to the staging area. If None, all changes are added.
        include_body (bool): If True, include a generated commit body with the changes in the commit message.
        skip_git (bool): If True, skip all Git operations and return immediately.

    Raises:
        GitRepositoryError: If the command fails.

    """

    # Check if Git operations should be skipped
    if skip_git or os.getenv("KST_DISABLE_GIT", "").lower() in ("1", "true", "yes"):
        console.debug("Skipping Git operations (disabled via flag or environment variable)")
        return

    git_root = locate_root(cd_path=cd_path, check_marker=False)

    # Set scope to kst root if not provided
    scope = scope if scope is not None else locate_root(cd_path=cd_path, check_marker=True)

    git("reset", cd_path=git_root, expected_exit_code=0)
    git("add", "--", str(scope), cd_path=git_root, expected_exit_code=0)

    try:
        # An exit code of 1 indicates that there are changes to commit
        stats = git(
            "diff",
            "--shortstat",
            "--staged",
            "--exit-code",
            cd_path=cd_path,
            expected_exit_code=1,
        ).stdout.strip()
    except GitRepositoryError:
        console.info("No changes to commit.")
        return

    if include_body:
        message += "\n\n" + generate_commit_body(cd_path, stage=True)

    git("commit", "-m", message, cd_path=cd_path, expected_exit_code=0)
    console.info(f"Changes committed. {stats}")
