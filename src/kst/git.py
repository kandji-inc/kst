import functools
import logging
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
    """Locate the root of the git repository.

    The result is cached to avoid repeated calls to git for the same path.

    Args:
        cd_path (Path): The path to run the git command from.

    Returns:
        Path: The root of the repository.

    Raises:
        FileNotFoundError: If the git executable is not found.
        InvalidRepositoryError: If a kst repository is not found.

    """

    cd_path = cd_path.expanduser().resolve()
    console.debug(f"Received git repository root search path: {cd_path}")

    # Search for a existing parent directory to start the search from
    if not cd_path.is_dir():
        for parent in cd_path.expanduser().resolve().parents:
            if parent == parent.parent:
                # Reached the root of the filesystem
                msg = f"Failed to locate an existing parent directory for {cd_path}"
                console.error(msg)
                raise InvalidRepositoryError(msg)
            if parent.is_dir():
                cd_path = parent
                break

    # Locate the root of the repository at cd_path if one exists
    console.debug(f"Starting git repository search from {cd_path}")
    try:
        result = git("rev-parse", "--show-toplevel", cd_path=cd_path, expected_exit_code=0)
        console.debug(f"Located git repository root at {result.stdout.strip()}")
    except GitRepositoryError as error:
        msg = f"Failed to locate the root of the repository for {cd_path}"
        console.error(msg)
        raise InvalidRepositoryError(msg) from error

    root = Path(result.stdout.strip()).expanduser().resolve()

    if check_marker and not (root / ".kst").is_file():
        console.error("The repository does not contain a .kst file at its root.")
        raise InvalidRepositoryError(
            "The repository does not appear to be a Kandji Sync Toolkit repository. If it should be, "
            'please make sure a ".kst" file exists in the root of the repository.'
        )
    return root


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


def changed_paths(*, cd_path: Path = Path("."), stage: bool = False) -> list[StatusPath]:
    """Get a list of changed paths in the repository.

    Args:
        cd_path (Path): The path to run the git command from.

    Returns:
        list[Path]: A list of changed paths.

    Raises:
        GitRepositoryError: If the command fails.

    """

    cmd = ["diff", "--name-status"]
    if stage:
        cmd.append("--staged")

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
    root = locate_root(cd_path=repo, check_marker=False)
    commit_body = ""
    for status, path in changed_paths(cd_path=root, stage=stage):
        if RepositoryDirectory.PROFILES in path.parts:
            changed["Profiles"][status].add(path)
        elif RepositoryDirectory.SCRIPTS in path.parts:
            changed["Scripts"][status].add(path)
        else:
            changed["Other"][status].add(path)

    for key, statuses in changed.items():
        for status, paths in statuses.items():
            commit_body += f"--- {key} {status} ---\n"
            for path in sorted(paths):
                commit_body += f"* {path.relative_to(root)}\n"
            commit_body += "\n"

    return commit_body.strip()


def commit_all_changes(
    *, cd_path: Path = Path("."), message: str, scope: Path | None = None, include_body: bool = True
) -> None:
    """Add all changed files to the staging area and commit with the specified commit message.

    Args:
        cd_path (Path): The path to run the git command from.
        message (str): The commit message.
        scope (Path | None): The path to add to the staging area. If None, all changes are added.

    Raises:
        GitRepositoryError: If the command fails.

    """

    root = locate_root(cd_path=cd_path, check_marker=False)

    git("reset", cd_path=root, expected_exit_code=0)
    if scope is None:
        git("add", "--all", cd_path=root, expected_exit_code=0)
    else:
        git("add", str(scope), cd_path=root, expected_exit_code=0)

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
