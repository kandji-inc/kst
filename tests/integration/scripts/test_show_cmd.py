import random

import pytest
from typer.testing import CliRunner

from kst import app

runner = CliRunner(mix_stderr=False)


@pytest.mark.parametrize("extra_args", [pytest.param(["--help"], id="--help"), pytest.param([], id="no args")])
def test_help(extra_args: list[str]):
    result = runner.invoke(app, ["script", "show", *extra_args])

    # Check that the command ran successfully
    assert result.exit_code == 0

    # Check that the help message contains the expected content
    assert "Usage: kst script show [OPTIONS] SCRIPT" in result.stdout


@pytest.mark.parametrize(
    ("by_id", "pass_remote", "by_parent"),
    [
        pytest.param(True, False, False, id="id-local"),
        pytest.param(False, False, False, id="path-local"),
        pytest.param(False, False, True, id="parent-local"),
        pytest.param(True, True, False, id="id-remote"),
        pytest.param(False, True, False, id="path-remote"),
        pytest.param(False, True, True, id="parent-remote"),
    ],
)
@pytest.mark.usefixtures("tmp_path_repo_cd")
def test_show_script(local_remote_changes, patch_scripts_endpoints, by_id: bool, pass_remote: bool, by_parent: bool):
    local, remote, _ = local_remote_changes

    cmd = ["script", "show"]
    if pass_remote:
        cmd.append("--remote")

    repo = remote if pass_remote else local

    # only use scripts which are in local repo since path could be passed to remote
    script = random.choice([script for script in repo.values() if script.id in local])

    # get the local script for script path option
    local_script = local[script.id]
    assert local_script.info_path is not None

    cmd.append(
        script.id
        if by_id
        else str(local_script.info_path)
        if by_parent
        else str(local_script.info_path.resolve().parent)
    )

    # sanity check for called_dict
    assert all(v == 0 for v in patch_scripts_endpoints.values())

    result = runner.invoke(app, cmd)

    # only git should be called and only if remote is passed
    assert all(v == 0 for k, v in patch_scripts_endpoints.items() if k not in {"list"})
    assert patch_scripts_endpoints["list"] == (1 if pass_remote else 0)

    # Check that the command ran successfully
    assert result.exit_code == 0

    # Check that the output contains the expected content
    assert script.id in result.stdout
    assert script.name in result.stdout


def test_show_from_outside_repo(local_remote_changes):
    local, _, _ = local_remote_changes
    script = random.choice(list(local.values()))

    result = runner.invoke(app, ["script", "show", "--repo", str(local.root), script.id])

    assert result.exit_code == 0

    assert script.id in result.stdout
    assert script.name in result.stdout


def test_show_from_outside_repo_with_path(local_remote_changes):
    local, _, _ = local_remote_changes
    script = random.choice(list(local.values()))

    result = runner.invoke(app, ["script", "show", str(script.info_path.parent)])

    assert result.exit_code == 0

    assert script.id in result.stdout
    assert script.name in result.stdout
