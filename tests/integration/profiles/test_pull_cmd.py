import random
import re
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from kst import app
from kst.diff import ChangeType
from kst.repository import CustomProfile, Repository

runner = CliRunner(mix_stderr=False)


def compare_profile_object(profile1, profile2, expected_diff):
    for k in set(profile1.info.model_dump().keys()):
        if k in expected_diff:
            assert getattr(profile1.info, k, None) != getattr(profile2.info, k, None)
        else:
            assert getattr(profile1.info, k, None) == getattr(profile2.info, k, None)

    if "profile" not in expected_diff:
        assert profile1.profile.content == profile2.profile.content
    else:
        assert profile1.profile.content != profile2.profile.content


def compare_profile_content(profile1, profile2, expected_diff):
    all_keys = set(profile1.profile.data.keys()) | set(profile2.profile.data.keys())
    for k in all_keys:
        if k in expected_diff:
            assert profile1.profile.data.get(k) != profile2.profile.data.get(k)
        else:
            assert profile1.profile.data.get(k) == profile2.profile.data.get(k)


def test_help():
    result = runner.invoke(app, ["profile", "pull", "--help"])
    assert result.exit_code == 0
    assert "Usage: kst profile pull" in result.stdout
    assert "Pull remote custom profiles changes from Kandji." in result.stdout
    assert "Made with ❤ by Kandji" in result.stdout


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_all_dry_run(local_remote_changes):
    local, _, _ = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    result = runner.invoke(app, ["profile", "pull", "--all", "--dry-run"])
    assert result.exit_code == 0

    # Check output
    assert "Running in dry-run mode" in result.stdout
    assert len(re.findall(r"Would have created profile:", result.stdout)) == 1
    assert len(re.findall(r"Would have updated profile:", result.stdout)) == 1
    assert len(re.findall(r"Would have deleted profile:", result.stdout)) == 0
    assert "Would have deleted profile:" not in result.stdout
    assert "Dry run complete. No changes were made." in result.stdout

    # Check no profiles have changed
    assert Repository.load_path(model=CustomProfile) == local


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_all_clean(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    result = runner.invoke(app, ["profile", "pull", "--all", "--clean"])
    assert result.exit_code == 0

    # Check output
    assert "Pulling 3 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo successfully", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo successfully", result.stdout)) == 1
    assert len(re.findall(r"deleted in local repo successfully", result.stdout)) == 1
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+1\s+0", result.stdout)
    assert re.search(r"Deleted\s+1\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Local only updates\s+1", result.stdout)
    assert re.search(r"Conflicting changes\s+1", result.stdout)

    repo = Repository.load_path(model=CustomProfile)

    # Check that the created profile's matches the remote
    remote_profile_from_changes = changes[ChangeType.CREATE_REMOTE][0][1]
    new_created_local_profile = repo[remote_profile_from_changes.id]
    compare_profile_object(remote_profile_from_changes, new_created_local_profile, {"sync_hash"})
    compare_profile_content(remote_profile_from_changes, new_created_local_profile, {})

    # Check that the updated profile has not changed.
    remote_profile = changes[ChangeType.UPDATE_REMOTE][0][1]
    compare_profile_object(remote_profile, repo[remote_profile.id], {"sync_hash"})
    compare_profile_content(remote_profile, repo[remote_profile.id], {})

    # Check that the deleted profile is still not in the repo
    deleted_id = changes[ChangeType.CREATE_LOCAL][0][0].id
    assert deleted_id not in repo


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_all_force(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    result = runner.invoke(app, ["profile", "pull", "--all", "--force"])
    assert result.exit_code == 0

    # Check output
    assert "Pulling 4 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo successfully", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo", result.stdout)) == 3
    assert len(re.findall(r"deleted in local repo successfully", result.stdout)) == 0
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Local only item\s+1", result.stdout)
    assert "Local only updates" not in result.stdout
    assert "Conflicting changes" not in result.stdout

    repo = Repository.load_path(model=CustomProfile)

    # Check that the created profile's matches the remote
    remote_profile_from_changes = changes[ChangeType.CREATE_REMOTE][0][1]
    new_created_local_profile = repo[remote_profile_from_changes.id]
    compare_profile_object(
        remote_profile_from_changes,
        new_created_local_profile,
        {"sync_hash", "profile_path", "info_path"},
    )
    compare_profile_content(remote_profile_from_changes, new_created_local_profile, {})

    # Check that the updated profile has not changed.
    for change_type in (ChangeType.UPDATE_REMOTE, ChangeType.CONFLICT):
        remote_profile = changes[change_type][0][1]
        compare_profile_object(remote_profile, repo[remote_profile.id], {"sync_hash"})
        compare_profile_content(remote_profile, repo[remote_profile.id], {})

    # check that the update_remote profile has been reverted to the local state
    remote_profile = changes[ChangeType.UPDATE_LOCAL][0][1]
    compare_profile_object(remote_profile, repo[remote_profile.id], {"sync_hash"})
    compare_profile_content(remote_profile, repo[remote_profile.id], {})


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_by_id_and_path(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    cmd_args = [
        "profile",
        "pull",
        "--force",
        "--id",
        changes[ChangeType.CREATE_REMOTE][0][1].id,
        "--path",
        str(changes[ChangeType.CREATE_LOCAL][0][0].profile_path.parent),
    ]
    for idx, change_type in enumerate(
        {k for k in changes if k not in {ChangeType.CREATE_REMOTE, ChangeType.CREATE_LOCAL}}
    ):
        if change_type in {ChangeType.CREATE_REMOTE, ChangeType.CREATE_LOCAL}:
            continue
        if idx % 2 == 1:
            cmd_args.append("--path")
            cmd_args.append(str(random.choice(changes[change_type])[0].profile_path.parent))
        else:
            cmd_args.append("--id")
            cmd_args.append(random.choice(changes[change_type])[0].id)
    result = runner.invoke(app, cmd_args)
    assert result.exit_code == 0

    # Check output
    assert "Pulling 4 changes from Kandji..." in result.stdout
    assert len(re.findall(r"created in local repo successfully", result.stdout)) == 1
    assert len(re.findall(r"updated in local repo", result.stdout)) == 3
    assert len(re.findall(r"deleted in local repo successfully", result.stdout)) == 0
    assert "Pull operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+1", result.stdout)
    assert re.search(r"Local only item\s+1", result.stdout)
    assert "Updated on remote only" not in result.stdout

    repo = Repository.load_path(model=CustomProfile)

    # Check that the updated profile has not changed.
    for change_type in (ChangeType.UPDATE_LOCAL, ChangeType.CONFLICT, ChangeType.UPDATE_REMOTE):
        remote_profile = changes[change_type][0][1]
        compare_profile_object(remote_profile, repo[remote_profile.id], {"sync_hash"})
        compare_profile_content(remote_profile, repo[remote_profile.id], {})


@pytest.mark.usefixtures("patch_profiles_endpoints", "local_remote_changes", "tmp_path_repo_cd")
def test_invalid_id():
    random_id = str(uuid4())
    result = runner.invoke(app, ["profile", "pull", "--force", "--id", random_id])
    assert result.exit_code == 2
    assert "Repository member with ID" in result.stderr
    assert f"{random_id} not found in local or remote" in result.stderr


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_invalid_path(local_remote_changes):
    local, _, _ = local_remote_changes

    missing_path = Path("profiles/invalid")
    assert not missing_path.exists()

    result = runner.invoke(app, ["profile", "pull", "--force", "--path", str(missing_path)])
    assert result.exit_code == 2
    assert "does not exist." in result.stderr
