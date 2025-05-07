import pytest
import typer

from kst.cli.profile import callback


def test_git_located(monkeypatch):
    """Ensure that locate_git is run when the profile command is executed."""
    called = False

    def mock_locate_git():
        nonlocal called
        called = True
        return "/usr/bin/git"

    monkeypatch.setattr("kst.git.locate_git", mock_locate_git)
    callback()
    assert called is True


def test_git_missing(monkeypatch):
    """Ensure that an error is raised if locate_git fails."""

    def mock_locate_git():
        raise FileNotFoundError("Failed to locate the git executable.")

    monkeypatch.setattr("kst.git.locate_git", mock_locate_git)
    with pytest.raises(typer.Exit) as ctx:
        callback()
    assert ctx.value.exit_code == 1
