"""Subprocess smoke tests validating the deprecation contract."""

import re
import subprocess
import sys
from pathlib import Path


def _run(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: PLW1510
        [sys.executable, "-m", "kst", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_version_format() -> None:
    result = _run("--version")
    assert result.returncode == 0
    assert re.match(r"^kst \S+, using iructl \S+$", result.stdout.strip()), (
        result.stdout
    )
    assert "warning: kst is deprecated; use iructl instead." in result.stderr


def test_version_after_value_bearing_option() -> None:
    # `--log` consumes the next token as its value; the wrapper must still
    # recognize the top-level `--version` that follows it.
    result = _run("--log", "debug", "--version")
    assert result.returncode == 0
    assert re.match(r"^kst \S+, using iructl \S+$", result.stdout.strip()), (
        result.stdout
    )


def test_cli_survives_warnings_as_errors() -> None:
    # The package-import DeprecationWarning is suppressed on the CLI path, so
    # `-W error` must not escalate it into a crash before the CLI runs. The
    # clean stderr notice is the CLI's sole deprecation signal.
    result = subprocess.run(  # noqa: PLW1510
        [sys.executable, "-W", "error", "-m", "kst", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert re.match(r"^kst \S+, using iructl \S+$", result.stdout.strip()), (
        result.stdout
    )
    assert "DeprecationWarning" not in result.stderr


def test_new_creates_kst_marker(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    result = _run("new", str(repo))
    assert result.returncode == 0, result.stderr
    assert (repo / ".kst").exists(), "expected .kst marker, not .iructl"
    assert not (repo / ".iructl").exists()


def test_env_vars_accepted() -> None:
    import os

    env = {
        **os.environ,
        "KST_TENANT": "https://example.api.iru.com",
        "KST_TOKEN": "test-token",
    }
    result = _run("profile", "list", "--help", env=env)
    assert result.returncode == 0, result.stderr


def test_kandji_branding_in_help() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "Kandji Sync Toolkit" in result.stdout
    assert "Iru Control" not in result.stdout


def test_kandji_branding_in_bundled_readme(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    result = _run("new", str(repo))
    assert result.returncode == 0, result.stderr
    readme = (repo / "README.md").read_text()
    assert "Kandji Sync Toolkit" in readme
