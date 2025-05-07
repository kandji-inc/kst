import itertools
import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import pytest
import requests
import typer

from kst.__about__ import APP_NAME
from kst.cli.utility import (
    filter_changes,
    get_local_members,
    get_remote_members,
    load_members_by_id,
    load_members_by_path,
    save_report,
)
from kst.diff import ChangeType
from kst.repository import PROFILE_RUNS_ON_PARAMS, CustomProfile, Repository


@pytest.mark.parametrize(
    ("pass_repo_path", "num_profiles", "add_invalid_id", "expectation", "log_message"),
    [
        pytest.param(False, 0, False, nullcontext(0), "", id="no_repo-no_ids"),
        pytest.param(
            False,
            1,
            False,
            pytest.raises(typer.Exit),
            "Failed to locate the root of the repository",
            id="no_repo-one_id",
        ),
        pytest.param(True, 0, False, nullcontext(0), "", id="repo-no_ids"),
        pytest.param(True, 1, False, nullcontext(1), "", id="repo-one_id"),
        pytest.param(True, 2, False, nullcontext(2), "", id="repo-multiple_ids"),
        pytest.param(
            True, 2, True, pytest.raises(typer.BadParameter), "not found in local repository", id="repo-invalid_id"
        ),
    ],
)
def test_get_profiles_from_repo_by_id(
    caplog,
    profiles_repo: Path,
    profiles_repo_obj: Repository,
    pass_repo_path,
    num_profiles,
    add_invalid_id,
    expectation,
    log_message,
):
    # Get profile ids from repo
    profile_ids = list(itertools.islice(profiles_repo_obj, num_profiles))
    assert len(profile_ids) == num_profiles  # Sanity check for num_profiles

    if add_invalid_id:
        profile_ids.append("invalid_id")

    with expectation as expected_length:
        result = load_members_by_id(
            repo_path=profiles_repo if pass_repo_path else Path("/var/tmp"),
            member_type=CustomProfile,
            member_ids=profile_ids,
        )
        assert len(list(result)) == expected_length

    assert log_message in caplog.text


@pytest.mark.parametrize(
    ("num_profiles", "add_invalid_path", "expectation", "log_message"),
    [
        pytest.param(
            0,
            False,
            nullcontext(0),
            "",
            id="no_paths",
        ),
        pytest.param(
            1,
            False,
            nullcontext(1),
            "",
            id="one_paths",
        ),
        pytest.param(
            2,
            False,
            nullcontext(2),
            "",
            id="multiple_paths",
        ),
        pytest.param(
            0,
            True,
            pytest.raises(typer.Exit),
            "An error occurred while loading",
            id="one_invalid_path",
        ),
        pytest.param(
            1,
            True,
            pytest.raises(typer.Exit),
            "An error occurred while loading",
            id="one_path-one_invalid_path",
        ),
    ],
)
def test_load_profiles_by_path(
    caplog, profiles_repo_obj: Repository, num_profiles, add_invalid_path, expectation, log_message
):
    # Get profile from repo

    profile_paths = [
        profile.profile_path
        for profile in itertools.islice(profiles_repo_obj.values(), num_profiles + int(add_invalid_path))
    ]
    assert len(profile_paths) == num_profiles + int(add_invalid_path)  # Sanity check for num_profiles

    if add_invalid_path:
        with profile_paths[-1].open("wb") as profile:
            profile.write(b"{invalid profile}")

    with expectation as expected_length:
        result = load_members_by_path(member_type=CustomProfile, member_paths=profile_paths)
        assert len(list(result)) == expected_length

    assert log_message in caplog.text


@pytest.mark.parametrize(
    ("pass_all", "num_paths", "num_ids", "num_duplicates", "expected_count"),
    [
        pytest.param(False, 0, 0, 0, 0, id="no_paths-no_ids"),
        pytest.param(False, 1, 0, 0, 1, id="one_path-no_ids"),
        pytest.param(False, 0, 1, 0, 1, id="no_paths-one_id"),
        pytest.param(False, 2, 1, 1, 2, id="remove_duplicates"),
        pytest.param(True, 0, 0, 0, 10, id="all"),
    ],
)
@pytest.mark.profile_count(10)
def test_get_local_profiles(
    profiles_repo: Path,
    profiles_repo_obj: Repository,
    pass_all,
    num_paths,
    num_ids,
    num_duplicates,
    expected_count,
):
    profiles_list = list(profiles_repo_obj.values())
    profile_paths = [profile.profile_path for profile in profiles_list][:num_paths]
    profile_ids = list(profiles_repo_obj)[num_paths - num_duplicates : num_ids]
    if len(profile_ids) != num_ids - num_duplicates or len(profile_paths) != num_paths:
        pytest.fail("Invalid test setup, unexpected number of profiles")

    result = get_local_members(
        repo=profiles_repo,
        member_type=CustomProfile,
        all_members=pass_all,
        member_paths=profile_paths,
        member_ids=profile_ids,
    )
    assert len(result) == expected_count

    for profile_path in profile_paths:
        assert result.get(str(profile_path)) is not None
    for profile_id in profile_ids:
        assert result.get(profile_id) is not None


@pytest.mark.parametrize(
    ("all_profiles", "num_ids", "add_missing", "expectation", "log_message"),
    [
        pytest.param(True, 0, False, nullcontext(9), "", id="all"),
        pytest.param(True, 2, False, nullcontext(9), "", id="all_with_ids"),
        pytest.param(False, 0, False, nullcontext(0), "", id="no_ids"),
        pytest.param(False, 2, False, nullcontext(2), "", id="with_ids"),
        pytest.param(False, 2, True, nullcontext(2), "", id="with_missing_ids"),
    ],
)
@pytest.mark.usefixtures("patch_profiles_endpoints", "local_remote_changes")
def test_get_remote_profiles(
    caplog,
    config,
    profiles_response,
    all_profiles,
    num_ids,
    add_missing,
    expectation,
    log_message,
):
    ids = [profile.id for profile in profiles_response.results[:num_ids]]
    if add_missing:
        ids.append(str(uuid4()))

    with expectation as expected_length:
        profiles = get_remote_members(
            config=config,
            member_type=CustomProfile,
            all_members=all_profiles,
            member_ids=ids,
            raise_on_missing=False,
        )
        assert len(profiles) == expected_length

    assert log_message in caplog.text


def test_get_remote_profiles_runs_on_missing(monkeypatch, config, profiles_response):
    """Check that if the API returns a profile with no runs_on parameters set, they default to True"""
    profile = profiles_response.results[0]

    def fake_list(self):
        for param in PROFILE_RUNS_ON_PARAMS:
            setattr(profile, param, False)
        return profiles_response

    monkeypatch.setattr("kst.api.profiles.CustomProfilesResource.list", fake_list)

    result_repo = get_remote_members(
        config=config,
        member_type=CustomProfile,
        member_ids=[profile.id],
    )
    assert all(getattr(result_repo[profile.id].info, param) for param in PROFILE_RUNS_ON_PARAMS)


def test_get_remote_profiles_connection_error(monkeypatch, caplog, config):
    def fake_list(self):
        raise requests.exceptions.ConnectionError("Connection Error")

    monkeypatch.setattr("kst.api.profiles.CustomProfilesResource.list", fake_list)
    with pytest.raises(typer.Exit):
        get_remote_members(
            config=config,
            member_type=CustomProfile,
            all_members=True,
        )

    assert "An error occurred while fetching: Connection Error" in caplog.text


def test_filter_changes(local_remote_changes):
    local_repo, remote_repo, expected_changes = local_remote_changes
    filtered_changes = filter_changes(local_repo, remote_repo)
    for change_type in ChangeType:
        result = sorted(filtered_changes[change_type], key=lambda x: x[0].id if x[0] is not None else "")
        expected = sorted(expected_changes[change_type], key=lambda x: x[0].id if x[0] is not None else "")
        assert len(result) == len(expected)
        assert result == expected


def test_save_report(profile_sync_results, tmp_path):
    """Test saving the sync report to a file."""
    report_path = tmp_path / f"{APP_NAME}_report.json"
    save_report(results=profile_sync_results, report_path=report_path)
    assert report_path.exists()
    original_size = report_path.stat().st_size
    with report_path.open("r") as f:
        data = json.load(f)
        assert len(data) == 1
        assert "success" in data[0]
        assert "failure" in data[0]
        assert len(data[0]["success"]) == len(profile_sync_results.success)
        assert len(data[0]["failure"]) == len(profile_sync_results.failure)

    save_report(results=profile_sync_results, report_path=report_path)
    assert original_size != report_path.stat().st_size
    with report_path.open("r") as f:
        data = json.load(f)
        assert len(data) == 2
