from uuid import uuid4

import pytest
from typer.testing import CliRunner

from kst import app

runner = CliRunner(mix_stderr=False)


@pytest.mark.usefixtures("tmp_path_cd")
def test_no_git_repo():
    profile_id = str(uuid4())
    results = {}
    results["list"] = runner.invoke(app, ["profile", "list"])
    results["pull"] = runner.invoke(app, ["profile", "pull", "--id", profile_id])
    results["push"] = runner.invoke(app, ["profile", "push", "--id", profile_id])
    results["sync"] = runner.invoke(app, ["profile", "sync", "--id", profile_id])
    results["delete"] = runner.invoke(app, ["profile", "delete", "--id", profile_id])

    for result in results.values():
        assert result.exit_code == 2
        assert "Invalid value" in result.stderr
        assert "is not a valid kst" in result.stderr


def test_git_repo_no_marker(git_repo):
    profile_id = str(uuid4())
    results = {}
    results["list"] = runner.invoke(app, ["profile", "list", "--repo", git_repo])
    results["pull"] = runner.invoke(app, ["profile", "pull", "--repo", git_repo, "--id", profile_id])
    results["push"] = runner.invoke(app, ["profile", "push", "--repo", git_repo, "--id", profile_id])
    results["sync"] = runner.invoke(app, ["profile", "sync", "--repo", git_repo, "--id", profile_id])
    results["delete"] = runner.invoke(app, ["profile", "delete", "--repo", git_repo, "--id", profile_id])

    for result in results.values():
        assert result.exit_code == 2
        assert "Invalid value" in result.stderr
        assert "is not a valid kst" in result.stderr
