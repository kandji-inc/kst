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
    result = runner.invoke(app, ["profile", "push", "--help"])
    assert result.exit_code == 0
    assert "Usage: kst profile push" in result.stdout
    assert "Push local custom profiles changes to Kandji." in result.stdout
    assert "Made with ❤ by Kandji" in result.stdout


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_all_dry_run(local_remote_changes):
    local, _, _ = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    result = runner.invoke(app, ["profile", "push", "--all", "--dry-run"])
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

    result = runner.invoke(app, ["profile", "push", "--all", "--clean"])
    assert result.exit_code == 0

    # Check output
    assert "Pushing 3 changes to Kandji..." in result.stdout
    assert len(re.findall(r"created in Kandji successfully", result.stdout)) == 1
    assert len(re.findall(r"updated in Kandji", result.stdout)) == 1
    assert len(re.findall(r"deleted in Kandji successfully", result.stdout)) == 1
    assert "Push operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+1\s+0", result.stdout)
    assert re.search(r"Deleted\s+1\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Remote only updates\s+1", result.stdout)
    assert re.search(r"Conflicting changes\s+1", result.stdout)

    repo = Repository.load_path(model=CustomProfile)

    # Check that the created profile's id has been updated along with dependent fields
    old_created_profile = changes[ChangeType.CREATE_LOCAL][0][0]
    new_created_profile = repo[str(old_created_profile.profile_path)]
    assert old_created_profile.id not in repo
    assert new_created_profile.id in repo
    compare_profile_object(
        old_created_profile,
        new_created_profile,
        {"id", "created_at", "updated_at", "sync_hash", "profile", "mdm_identifier"},
    )
    compare_profile_content(
        old_created_profile,
        new_created_profile,
        {"PayloadUUID", "PayloadIdentifier"},
    )

    # Check that the updated profile has not changed.
    # The profiles changes in this case because it's PayloadDisplayName is set to match the info file name field
    updated_id = changes[ChangeType.UPDATE_LOCAL][0][0].id
    compare_profile_object(local[updated_id], repo[updated_id], {"updated_at", "sync_hash", "profile"})
    compare_profile_content(local[updated_id], repo[updated_id], {"PayloadDisplayName"})

    # Check that the deleted profile is still not in the repo
    deleted_id = changes[ChangeType.CREATE_REMOTE][0][1].id
    assert deleted_id not in repo


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_all_force(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    result = runner.invoke(app, ["profile", "push", "--all", "--force"])
    assert result.exit_code == 0

    # Check output
    assert "Pushing 4 changes to Kandji..." in result.stdout
    assert len(re.findall(r"created in Kandji successfully with new Kandji ID:", result.stdout)) == 1
    assert len(re.findall(r"updated in Kandji", result.stdout)) == 3
    assert len(re.findall(r"deleted in Kandji successfully", result.stdout)) == 0
    assert "Push operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+5", result.stdout)
    assert re.search(r"Remote only item\s+1", result.stdout)
    assert "Updated on remote only" not in result.stdout

    repo = Repository.load_path(model=CustomProfile)

    # Check that the created profile's id has been updated along with dependent fields
    old_created_profile = changes[ChangeType.CREATE_LOCAL][0][0]
    new_created_profile = repo[str(old_created_profile.profile_path)]
    assert old_created_profile.id not in repo
    assert new_created_profile.id in repo
    compare_profile_object(
        old_created_profile,
        new_created_profile,
        {"id", "created_at", "updated_at", "sync_hash", "profile", "mdm_identifier"},
    )
    compare_profile_content(
        old_created_profile,
        new_created_profile,
        {"PayloadUUID", "PayloadIdentifier"},
    )

    # Check that the updated profile has not changed.
    # The profiles changes in this case because it's PayloadDisplayName is set to match the info file name field
    for change_type in (ChangeType.UPDATE_LOCAL, ChangeType.CONFLICT):
        updated_id = changes[change_type][0][0].id
        compare_profile_object(local[updated_id], repo[updated_id], {"updated_at", "sync_hash", "profile"})
        compare_profile_content(local[updated_id], repo[updated_id], {"PayloadDisplayName"})

    # check that the update_remote profile has been reverted to the local state
    updated_id = changes[ChangeType.UPDATE_REMOTE][0][0].id
    compare_profile_object(local[updated_id], repo[updated_id], {"updated_at"})
    compare_profile_content(local[updated_id], repo[updated_id], {})


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_by_id_and_path(local_remote_changes):
    local, _, changes = local_remote_changes

    # Sanity check that local repo matches disk
    assert Repository.load_path(model=CustomProfile) == local

    cmd_args = ["profile", "push", "--force", "--id", changes[ChangeType.CREATE_REMOTE][0][1].id]
    for idx, change_type in enumerate(changes):
        if change_type == ChangeType.CREATE_REMOTE:
            continue
        if idx % 2 == 0:
            cmd_args.append("--path")
            cmd_args.append(random.choice(changes[change_type])[0].profile_path.parent)
        else:
            cmd_args.append("--id")
            cmd_args.append(random.choice(changes[change_type])[0].id)
    result = runner.invoke(app, cmd_args)
    assert result.exit_code == 0

    # Check output
    assert "Pushing 4 changes to Kandji..." in result.stdout
    assert len(re.findall(r"created in Kandji successfully with new Kandji ID:", result.stdout)) == 1
    assert len(re.findall(r"updated in Kandji", result.stdout)) == 3
    assert len(re.findall(r"deleted in Kandji successfully", result.stdout)) == 0
    assert "Push operation complete!" in result.stdout
    assert "Updated Item Summary" in result.stdout
    assert re.search(r"Created\s+1\s+0", result.stdout)
    assert re.search(r"Updated\s+3\s+0", result.stdout)
    assert "Skipped Item Summary" in result.stdout
    assert re.search(r"Already up to date\s+1", result.stdout)
    assert re.search(r"Remote only item\s+1", result.stdout)
    assert "Updated on remote only" not in result.stdout

    repo = Repository.load_path(model=CustomProfile)

    # Check that the created profile's id has been updated along with dependent fields
    old_created_profile = changes[ChangeType.CREATE_LOCAL][0][0]
    new_created_profile = repo[str(old_created_profile.profile_path)]
    assert old_created_profile.id not in repo
    assert new_created_profile.id in repo
    compare_profile_object(
        old_created_profile,
        new_created_profile,
        {"id", "created_at", "updated_at", "sync_hash", "profile", "mdm_identifier"},
    )
    compare_profile_content(
        old_created_profile,
        new_created_profile,
        {"PayloadUUID", "PayloadIdentifier"},
    )

    # Check that the updated profile has not changed.
    # The profiles changes in this case because it's PayloadDisplayName is set to match the info file name field
    for change_type in (ChangeType.UPDATE_LOCAL, ChangeType.CONFLICT):
        updated_id = changes[change_type][0][0].id
        compare_profile_object(local[updated_id], repo[updated_id], {"updated_at", "sync_hash", "profile"})
        compare_profile_content(local[updated_id], repo[updated_id], {"PayloadDisplayName"})

    # check that the update_remote profile has been reverted to the local state
    updated_id = changes[ChangeType.UPDATE_REMOTE][0][0].id
    compare_profile_object(local[updated_id], repo[updated_id], {"updated_at"})
    compare_profile_content(local[updated_id], repo[updated_id], {})


@pytest.mark.usefixtures("patch_profiles_endpoints", "local_remote_changes", "tmp_path_repo_cd")
def test_invalid_id():
    random_id = str(uuid4())
    result = runner.invoke(app, ["profile", "push", "--force", "--id", random_id])
    assert result.exit_code == 2
    assert "Repository member with ID" in result.stderr
    assert f"{random_id} not found in local or remote" in result.stderr


@pytest.mark.usefixtures("patch_profiles_endpoints", "tmp_path_repo_cd")
def test_invalid_path(local_remote_changes):
    local, _, _ = local_remote_changes

    missing_path = Path("profiles/invalid")
    assert not missing_path.exists()

    result = runner.invoke(app, ["profile", "push", "--force", "--path", str(missing_path)])
    assert result.exit_code == 2
    assert "does not exist." in result.stderr
