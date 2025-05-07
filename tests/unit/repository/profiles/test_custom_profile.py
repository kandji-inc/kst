import plistlib
import shutil
from pathlib import Path

import pytest

from kst.api import CustomProfilePayload
from kst.exceptions import (
    DuplicateInfoFileError,
    DuplicateProfileError,
    InvalidProfileError,
    MissingInfoFileError,
)
from kst.repository import ACCEPTED_INFO_EXTENSIONS, PROFILE_RUNS_ON_PARAMS, CustomProfile


@pytest.fixture
def profile_directory_mobileconfig(profile_directory: Path):
    """Return the path to a valid mobileconfig files in the profile directory."""
    return next(profile_directory.glob("*.mobileconfig"))


@pytest.fixture
def profile_directory_info_file(profile_directory: Path) -> Path:
    """Return the path to a valid info file in the profile directory."""
    return next(profile_directory.glob("info.*"))


@pytest.fixture
def profile_directory_without_profile(profile_directory: Path, profile_directory_mobileconfig: Path) -> Path:
    """Return the path to a profile directory without a mobileconfig file."""
    profile_directory_mobileconfig.unlink()
    return profile_directory


@pytest.fixture
def profile_directory_with_extra_profile(profile_directory: Path, profile_directory_mobileconfig: Path) -> Path:
    """Return the path to a profile directory with an extra mobileconfig file."""
    shutil.copy(profile_directory_mobileconfig, profile_directory_mobileconfig.with_name("extra.mobileconfig"))
    return profile_directory


@pytest.fixture
def profile_directory_without_info_file(profile_directory: Path, profile_directory_info_file: Path) -> Path:
    """Return the path to a profile directory without a mobileconfig file."""
    profile_directory_info_file.unlink()
    return profile_directory


@pytest.fixture
def profile_directory_with_extra_info_file(profile_directory: Path, profile_directory_info_file: Path) -> Path:
    """Return the path to a profile directory with an extra mobileconfig file."""
    suffix = (ACCEPTED_INFO_EXTENSIONS - {profile_directory_info_file.suffix}).pop()
    shutil.copy(profile_directory_info_file, profile_directory_info_file.with_name(f"info{suffix}"))
    return profile_directory


class TestMemberBase:
    """
    Tests for the MemberBase class. Since this class is abstract and cannot be
    instantiated, its subclass CustomProfile will be used for testing.
    """

    def test_info_path_raises_if_unset(self, custom_profile_obj):
        """Ensure the info_path property raises a ValueError if the info_path is unset."""
        assert custom_profile_obj.info.path is None
        with pytest.raises(ValueError, match="The info_path property must be set before reading."):
            custom_profile_obj.info_path

    def test_diff_hash(self, custom_profile_obj):
        """Ensure the diff_hash property is changes if a diffable property of any attribute changes."""
        # Hash should always exist in a CustomProfile object
        original_hash = custom_profile_obj.diff_hash
        assert original_hash is not None

        # Modify the info file
        original_name = custom_profile_obj.info.name
        custom_profile_obj.info.name = "New Profile Name"
        assert custom_profile_obj.diff_hash != original_hash
        custom_profile_obj.name = original_name
        assert custom_profile_obj.diff_hash == original_hash

        # Modify the profile file
        original_content = custom_profile_obj.profile.content
        data = plistlib.loads(original_content)
        data["PayloadDisplayName"] = "New Payload Display Name"
        custom_profile_obj.profile.content = plistlib.dumps(data, fmt=plistlib.FMT_XML).decode()
        assert custom_profile_obj.diff_hash != original_hash
        custom_profile_obj.profile.content = original_content
        assert custom_profile_obj.diff_hash == original_hash

    def test_updated(self, custom_profile_obj):
        """Ensure the updated method returns a new object with updated attributes."""
        profile_copy = custom_profile_obj.model_copy(deep=True)
        assert profile_copy is not custom_profile_obj
        assert profile_copy.info is not custom_profile_obj.info
        assert profile_copy.profile is not custom_profile_obj.profile
        assert profile_copy.diff_hash == custom_profile_obj.diff_hash

        new_name = "New Profile Name"
        profile_copy.name = new_name
        assert custom_profile_obj.name != new_name
        updated_profile = custom_profile_obj.updated(profile_copy)
        assert updated_profile.name == "New Profile Name"
        assert updated_profile.diff_hash != custom_profile_obj.diff_hash
        assert updated_profile.diff_hash == profile_copy.diff_hash

    def test_has_paths(self, custom_profile_obj):
        """Ensure the has_paths property returns True if both info_path and profile_path are set."""
        assert not custom_profile_obj.has_paths
        custom_profile_obj.info.path = Path("info.plist")
        assert not custom_profile_obj.has_paths
        custom_profile_obj.profile.path = Path("profile.mobileconfig")
        assert custom_profile_obj.has_paths


class TestCustomProfile:
    def test_profile_path_raises_if_unset(self, custom_profile_obj):
        """Ensure the profile_path property raises a ValueError if the profile_path is unset."""
        assert custom_profile_obj.profile.path is None
        with pytest.raises(ValueError, match="The profile_path property must be set before reading."):
            custom_profile_obj.profile_path

    def test_ensure_paths_without_paths(self, custom_profile_obj, profiles_repo):
        """Ensure the ensure_paths method sets the info_path and profile_path properties."""
        expected_info_path = profiles_repo / custom_profile_obj.name / f"info.{custom_profile_obj.info.format}"
        expected_profile_path = profiles_repo / custom_profile_obj.name / "profile.mobileconfig"

        assert not custom_profile_obj.has_paths
        custom_profile_obj.ensure_paths(profiles_repo)
        assert custom_profile_obj.has_paths
        assert custom_profile_obj.info_path == expected_info_path
        assert custom_profile_obj.profile_path == expected_profile_path

    def test_ensure_paths_with_paths(self, custom_profile_obj, profiles_repo):
        """Ensure the ensure_paths method does nothing if the paths are already set."""
        expected_info_path = profiles_repo / "What a Neat Profile" / f"info.{custom_profile_obj.info.format}"
        expected_profile_path = profiles_repo / "What a Neat Profile" / "profile.mobileconfig"
        custom_profile_obj.info_path = expected_info_path
        custom_profile_obj.profile_path = expected_profile_path
        custom_profile_obj.ensure_paths(profiles_repo)
        assert custom_profile_obj.info_path == expected_info_path
        assert custom_profile_obj.profile_path == expected_profile_path

    def test_ensure_paths_with_existing_parent(self, custom_profile_obj, profiles_repo):
        """Ensure the ensure_paths method increments the path if the parent directory already exists."""
        (profiles_repo / custom_profile_obj.name).mkdir()
        expected_info_path = profiles_repo / f"{custom_profile_obj.name} (1)" / f"info.{custom_profile_obj.info.format}"
        expected_profile_path = profiles_repo / f"{custom_profile_obj.name} (1)" / "profile.mobileconfig"

        assert not custom_profile_obj.has_paths
        custom_profile_obj.ensure_paths(profiles_repo)
        assert custom_profile_obj.has_paths
        assert custom_profile_obj.info_path == expected_info_path
        assert custom_profile_obj.profile_path == expected_profile_path

    def test_write_to_path(self, profiles_repo, custom_profile_obj):
        """Writing to disk should create a file both the info and profile files."""
        custom_profile_obj.ensure_paths(profiles_repo)

        # Check that files don't exist
        assert not custom_profile_obj.info_path.exists()
        assert not custom_profile_obj.profile_path.exists()

        custom_profile_obj.write()

        # Check that files were written
        assert custom_profile_obj.info_path.exists()
        assert custom_profile_obj.profile_path.exists()

    def test_write_to_path_without_paths(self, custom_profile_obj: CustomProfile):
        """Writing to disk with no info_path or profile_path should raise a InvalidProfileError."""
        assert custom_profile_obj.info.path is None
        assert custom_profile_obj.profile.path is None

        with pytest.raises(
            ValueError, match="The info_path and profile_path properties must be set before writing the profile."
        ):
            custom_profile_obj.write()

    def test_write_raises_on_different_parent_directories(self, profiles_repo: Path, custom_profile_obj: CustomProfile):
        """Writing to disk with info_path and profile_path in different directories should raise a InvalidProfileError."""
        custom_profile_obj.info_path = profiles_repo / "dir01/info.plist"
        custom_profile_obj.profile_path = profiles_repo / "dir02/profile.mobileconfig"
        with pytest.raises(InvalidProfileError, match=r"must be paths to files within the same directory"):
            custom_profile_obj.write()

    def test_from_api_payload(self, profile_info_data_factory, mobileconfig_content):
        profile_payload = CustomProfilePayload.model_validate(
            profile_info_data_factory() | {"profile": mobileconfig_content}
        )
        profile = CustomProfile.from_api_payload(profile_payload)
        assert isinstance(profile, CustomProfile)

        # Check that all false patch works
        for param in PROFILE_RUNS_ON_PARAMS:
            setattr(profile_payload, param, False)
        profile = CustomProfile.from_api_payload(profile_payload)
        assert all(getattr(profile.info, param) for param in PROFILE_RUNS_ON_PARAMS)

    def test_to_api_payload(self, custom_profile_obj):
        """Ensure the to_api_payload method returns a valid API payload."""
        custom_profile_obj.to_api_payload()

    def test_load_from_info_path(self, profile_directory_info_file):
        """Ensure creating a CustomProfile from a valid info file succeeds."""
        assert isinstance(CustomProfile.from_path(profile_directory_info_file), CustomProfile)

    def test_load_from_profile_path(self, profile_directory_mobileconfig):
        """Ensure creating a CustomProfile from a valid profile succeeds."""
        assert isinstance(CustomProfile.from_path(profile_directory_mobileconfig), CustomProfile)

    def test_load_from_directory_path(self, profile_directory):
        """Ensure creating a CustomProfile from a valid profile directory succeeds."""
        assert isinstance(CustomProfile.from_path(profile_directory), CustomProfile)

    @pytest.mark.usefixtures("profile_directory_without_profile")
    def test_load_with_missing_mobileconfig(self, profile_directory: Path):
        """Creating a CustomProfile from an info file that doesn't have a matching profile should raise a InvalidProfileError."""
        CustomProfile.from_path(profile_directory)
        assert (profile_directory / "profile.mobileconfig").is_file()

    @pytest.mark.usefixtures("profile_directory_with_extra_profile")
    def test_load_with_extra_mobileconfig(self, profile_directory):
        """Creating a CustomProfile from an info file that has an extra profile should raise a InvalidProfileError."""
        with pytest.raises(DuplicateProfileError):
            CustomProfile.from_path(profile_directory)

    @pytest.mark.usefixtures("profile_directory_without_info_file")
    def test_load_with_missing_info_file(self, profile_directory):
        """Creating a CustomProfile from a profile file without a matching info file should raise a InvalidProfileError."""
        with pytest.raises(MissingInfoFileError):
            CustomProfile.from_path(profile_directory)

    @pytest.mark.usefixtures("profile_directory_with_extra_info_file")
    def test_load_with_extra_info_file(self, profile_directory):
        """Creating a CustomProfile from a profile file that has an extra info file should raise a InvalidProfileError."""
        with pytest.raises(DuplicateInfoFileError):
            CustomProfile.from_path(profile_directory)

    def test_diff_hash(self, custom_profile_obj):
        """Test that the diff_hash property is correctly calculated."""

        # Hash should always exist in a CustomProfile object
        original_hash = custom_profile_obj.diff_hash
        assert original_hash is not None

        # Modify the info file
        original_name = custom_profile_obj.name
        custom_profile_obj.name = "New Profile Name"
        assert custom_profile_obj.diff_hash != original_hash
        custom_profile_obj.name = original_name
        assert custom_profile_obj.diff_hash == original_hash

        # Modify the profile file
        original_content = custom_profile_obj.profile.content
        data = plistlib.loads(original_content)
        data["PayloadDisplayName"] = "New Payload Display Name"
        custom_profile_obj.profile.content = plistlib.dumps(data, fmt=plistlib.FMT_XML).decode()
        assert custom_profile_obj.diff_hash != original_hash
        custom_profile_obj.profile.content = original_content
        assert custom_profile_obj.diff_hash == original_hash
