import random
import re
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from kst import app
from kst.diff import ChangeType
from kst.repository import CustomScript, Repository

runner = CliRunner(mix_stderr=False)


def compare_script_object(script1, script2, expected_diff):
    for k in set(script1.info.model_dump().keys()):
        if k in expected_diff:
            assert getattr(script1.info, k, None) != getattr(script2.info, k, None)
        else:
            assert getattr(script1.info, k, None) == getattr(script2.info, k, None)

    if "audit" not in expected_diff:
        assert script1.audit.content == script2.audit.content
    else:
        assert script1.audit.content != script2.audit.content

    if script1.remediation is None and script2.remediation is None:
        assert "remediation" not in expected_diff
    elif script1.remediation is None or script2.remediation is None:
        assert "remediation" in expected_diff
    elif script1.remediation.content == script2.remediation.content:
        assert "remediation" not in expected_diff
    elif script1.remediation.content != script2.remediation.content:
        assert "remediation" in expected_diff
    else:
        raise pytest.fail("Remediation script comparison got unexpected input.")


def test_help():
    result = runner.invoke(app, ["script", "pull", "--help"])
    assert result.exit_code == 0
    assert "Usage: kst script pull" in result.stdout
    assert "Pull remote custom scripts changes from Kandji." in result.stdout
    assert "Made with ❤ by Kandji" in result.stdout


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_all_dry_run(local_remote_changes):
    local, _, _ = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomScript) == local

    result = runner.invoke(app, ["script", "pull", "--all", "--dry-run"])
    assert result.exit_code == 0

    # Check output
    assert "Running in dry-run mode" in result.stdout
    assert len(re.findall(r"Would have created script:", result.stdout)) == 1
    assert len(re.findall(r"Would have updated script:", result.stdout)) == 1
    assert len(re.findall(r"Would have deleted script:", result.stdout)) == 0
    assert "Would have deleted script:" not in result.stdout
    assert "Dry run complete. No changes were made." in result.stdout

    # Check no scripts have changed
    assert Repository.load_path(model=CustomScript) == local


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_all_clean(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomScript) == local

    result = runner.invoke(app, ["script", "pull", "--all", "--clean"])
    assert result.exit_code == 0

    # Check output
    assert "Pulling 3 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo", result.stdout)) == 1
    assert len(re.findall(r"deleted in local repo", result.stdout)) == 1
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+1\s+0", result.stdout)
    assert re.search(r"Deleted\s+1\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Local only updates\s+1", result.stdout)
    assert re.search(r"Conflicting changes\s+1", result.stdout)

    repo = Repository.load_path(model=CustomScript)

    # Check that the created scripts match the remote
    remote_script_from_changes = changes[ChangeType.CREATE_REMOTE][0][1]
    new_created_local_script = repo[remote_script_from_changes.id]
    compare_script_object(remote_script_from_changes, new_created_local_script, {"sync_hash"})

    # Check that the updated script has not changed
    remote_script = changes[ChangeType.UPDATE_REMOTE][0][1]
    compare_script_object(remote_script, repo[remote_script.id], {"sync_hash"})

    # Check that the deleted script is still not in the repo
    deleted_id = changes[ChangeType.CREATE_LOCAL][0][0].id
    assert deleted_id not in repo


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_all_force(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomScript) == local

    result = runner.invoke(app, ["script", "pull", "--all", "--force"])
    assert result.exit_code == 0

    # Check output
    assert "Pulling 4 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo", result.stdout)) == 3
    assert len(re.findall(r"deleted in local repo", result.stdout)) == 0
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Local only item\s+1", result.stdout)
    assert "Local only updates" not in result.stdout
    assert "Conflicting changes" not in result.stdout

    repo = Repository.load_path(model=CustomScript)

    # Check that the created scripts match the remote
    remote_script_from_changes = changes[ChangeType.CREATE_REMOTE][0][1]
    new_created_local_script = repo[remote_script_from_changes.id]
    compare_script_object(
        remote_script_from_changes,
        new_created_local_script,
        {"sync_hash", "audit_path", "remediation_path", "info_path"},
    )

    # Check that the updated script has not changed
    for change_type in (ChangeType.UPDATE_REMOTE, ChangeType.CONFLICT):
        remote_script = changes[change_type][0][1]
        compare_script_object(remote_script, repo[remote_script.id], {"sync_hash"})

    # Check that the update_remote script has been reverted to the local state
    remote_script = changes[ChangeType.UPDATE_LOCAL][0][1]
    compare_script_object(remote_script, repo[remote_script.id], {"sync_hash"})


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_by_id_and_path(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomScript) == local

    cmd_args = [
        "script",
        "pull",
        "--force",
        "--id",
        changes[ChangeType.CREATE_REMOTE][0][1].id,
        "--path",
        str(changes[ChangeType.CREATE_LOCAL][0][0].info_path.parent),
    ]
    for idx, change_type in enumerate(
        {k for k in changes if k not in {ChangeType.CREATE_REMOTE, ChangeType.CREATE_LOCAL}}
    ):
        if change_type in {ChangeType.CREATE_REMOTE, ChangeType.CREATE_LOCAL}:
            continue
        if idx % 2 == 1:
            cmd_args.append("--path")
            cmd_args.append(str(random.choice(changes[change_type])[0].info_path.parent))
        else:
            cmd_args.append("--id")
            cmd_args.append(random.choice(changes[change_type])[0].id)
    result = runner.invoke(app, cmd_args)
    assert result.exit_code == 0

    # Check output
    assert "Pulling 4 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo", result.stdout)) == 3
    assert len(re.findall(r"deleted in local repo", result.stdout)) == 0
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+1", result.stdout)
    assert re.search(r"Local only item\s+1", result.stdout)
    assert "Updated on remote only" not in result.stdout

    repo = Repository.load_path(model=CustomScript)

    # Check that the updated script has not changed
    for change_type in (ChangeType.UPDATE_LOCAL, ChangeType.CONFLICT, ChangeType.UPDATE_REMOTE):
        remote_script = changes[change_type][0][1]
        compare_script_object(remote_script, repo[remote_script.id], {"sync_hash"})


@pytest.mark.usefixtures("patch_scripts_endpoints", "local_remote_changes", "tmp_path_repo_cd")
def test_invalid_id():
    random_id = str(uuid4())
    result = runner.invoke(app, ["script", "pull", "--force", "--id", random_id])
    assert result.exit_code == 2
    assert "Repository member with ID" in result.stderr
    assert f"{random_id} not found in" in result.stderr


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_invalid_path(local_remote_changes):
    local, _, _ = local_remote_changes

    missing_path = Path("scripts/invalid")
    assert not missing_path.exists()

    result = runner.invoke(app, ["script", "pull", "--force", "--path", str(missing_path)])
    assert result.exit_code == 2
    assert "does not exist." in result.stderr


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_add_remediation_script(local_remote_changes):
    local, remote, changes = local_remote_changes

    # add a remediation script to the remote repo
    script_id = changes[ChangeType.UPDATE_REMOTE][0][1].id
    local_script_path = local[script_id].info_path
    local[script_id].remediation = None
    remote[script_id].remediation.content = "echo 'Hello World!'"

    result = runner.invoke(app, ["script", "pull", "--id", script_id])

    assert result.exit_code == 0
    updated_local_script = CustomScript.from_path(local_script_path)
    assert updated_local_script.remediation is not None
    assert updated_local_script.remediation.content == "echo 'Hello World!'"


@pytest.mark.usefixtures("patch_scripts_endpoints", "tmp_path_repo_cd")
def test_remove_remediation_script(local_remote_changes):
    local, remote, changes = local_remote_changes

    # add a remediation script to the remote repo
    script_id = changes[ChangeType.UPDATE_REMOTE][0][1].id
    local_script_path = local[script_id].info_path
    local[script_id].remediation.content = "echo 'Hello World!'"
    remote[script_id].remediation = None

    result = runner.invoke(app, ["script", "pull", "--id", script_id])

    assert result.exit_code == 0
    updated_local_script = CustomScript.from_path(local_script_path)
    assert updated_local_script.remediation is None
