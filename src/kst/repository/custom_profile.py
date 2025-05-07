import plistlib
from pathlib import Path
from typing import Self, override

from rich.syntax import Syntax
from rich.table import Table
from ruamel.yaml.scalarstring import LiteralScalarString

from kst import git
from kst.api import ApiConfig, CustomProfilePayload, CustomProfilesResource, PayloadList
from kst.console import SyntaxType
from kst.exceptions import (
    DuplicateInfoFileError,
    DuplicateProfileError,
    InvalidProfileError,
    MissingInfoFileError,
    MissingProfileError,
)
from kst.utils import sanitize_filename

from .content import Mobileconfig
from .info import ACCEPTED_INFO_EXTENSIONS, PROFILE_RUNS_ON_PARAMS, ProfileInfoFile
from .member_base import MemberBase

DIRECTORY_NAME = "profiles"


class CustomProfile(MemberBase):
    """A data model for representing a custom profile."""

    info: ProfileInfoFile
    profile: Mobileconfig

    @property
    def profile_path(self) -> Path:
        """Get the path to the profile file."""
        if self.profile.path is None:
            raise ValueError("The profile_path property must be set before reading.")
        return self.profile.path

    @profile_path.setter
    def profile_path(self, value: Path) -> None:
        """Set the path to the profile file."""
        self.profile.path = value

    @override
    def ensure_paths(self, repo_path: Path) -> None:
        """Set the info_path and profile_path properties to valid default paths within the repository.

        Raises:
            InvalidRepositoryError: repo_path is not a valid Kandji Sync Toolkit repository.
        """
        if self.has_paths:
            return  # Nothing to do here

        repo_path = repo_path.resolve()
        profiles_root = git.locate_root(cd_path=repo_path) / "profiles"

        profile_parent = (repo_path if repo_path.is_relative_to(profiles_root) else profiles_root) / sanitize_filename(
            self.info.name
        )

        # If output path already exists, increment the path with a number
        count = 0
        while profile_parent.exists():
            count += 1
            profile_parent = profile_parent.parent / f"{sanitize_filename(self.info.name)} ({count})"

        self.info.path = profile_parent / f"info.{self.info.format}"
        self.profile.path = profile_parent / "profile.mobileconfig"

    @override
    def write(self, write_content=True) -> None:
        """Save the CustomProfile object to the file system at the profile_path and info_path locations."""
        # Ensure valid profile path and info path are set
        if not self.has_paths:
            raise ValueError("The info_path and profile_path properties must be set before writing the profile.")

        # Verify that the info_path and profile_path are in the same directory
        if self.info_path.parent != self.profile_path.parent:
            raise InvalidProfileError(
                f"The info_path and profile_path properties must be paths to files within the same directory ({self.info_path.parent} != {self.profile_path.parent})."
            )

        # Create missing directories if they do not exist
        self.info_path.parent.mkdir(parents=True, exist_ok=True)

        # Write info to file
        self.info.write()

        # Write profile to file
        if write_content:
            self.profile.write()

    @override
    @classmethod
    def from_api_payload(cls, payload: CustomProfilePayload) -> Self:
        """Create a CustomProfile object from an API payload."""
        # patch profiles to handle all runs_on parameters being false. This was possible in older versions of Kandji
        # before the runs_on parameter was required.
        if all(getattr(payload, param) is False for param in PROFILE_RUNS_ON_PARAMS):
            for param in PROFILE_RUNS_ON_PARAMS:
                setattr(payload, param, True)

        info_file = ProfileInfoFile.model_validate(payload.model_dump(exclude={"profile"}))
        mobileconfig = Mobileconfig(content=payload.profile)

        return cls(info=info_file, profile=mobileconfig)

    @override
    def to_api_payload(self) -> CustomProfilePayload:
        """Convert to a CustomProfilePayload object."""

        profile_dict = self.info.model_dump(exclude={"sync_hash"}) | {"profile": self.profile.content}
        if profile_dict["updated_at"] is None:
            profile_dict["updated_at"] = self.info.created_at

        return CustomProfilePayload.model_validate(profile_dict)

    @override
    @classmethod
    def from_path(cls, path: Path, generate: bool = True) -> Self:
        """Load a CustomProfile object from a file path.

        The path can be the path to an info file, a mobileconfig file, or a directory containing both files.

        Args:
            path (Path): The path to load from.

        Returns:
            A CustomProfile object with data loaded from the file system.

        Raises:
            InvalidInfoFileError: If the info file is not a valid plist, json, or yaml file.
            InvalidProfileError: If the mobileconfig is not a valid plist.

        """

        # Set the profile directory path which will contain the info and mobileconfig files
        parent_path = (path.parent if path.is_file() else path).resolve()

        # Locate info file and ensure there are no duplicates
        info_path = [p for p in parent_path.glob("info.*") if p.suffix in ACCEPTED_INFO_EXTENSIONS]
        if len(info_path) == 0:
            raise MissingInfoFileError(
                f"Unable to locate info file at {parent_path}. Expected format: info.<plist|json|yml|yaml>"
            )
        if len(info_path) > 1:
            raise DuplicateInfoFileError(f"Multiple info files exist at {parent_path}.")
        info_path = info_path[0].resolve()
        info_file = ProfileInfoFile.load(info_path)

        # Locate mobileconfig file and ensure there are no duplicates
        mobileconfig_path = list(parent_path.glob("*.mobileconfig"))
        if len(mobileconfig_path) == 0:
            if generate:
                # If the mobileconfig file does not exist, create a new one
                mobileconfig_path = [parent_path / "profile.mobileconfig"]
                mobileconfig_path[0].write_text(Mobileconfig.default_content(_id=info_file.id, name=parent_path.stem))
            else:
                raise MissingProfileError(f"Unable to locate mobileconfig file at {parent_path}.")
        elif len(mobileconfig_path) > 1:
            raise DuplicateProfileError(
                f"Multiple mobileconfig files exist at {parent_path}. Ensure only one file exits with the .mobileconfig extension.\n* {'\n* '.join(str(p for p in mobileconfig_path))}"
            )
        mobileconfig_path = mobileconfig_path[0].resolve()
        mobileconfig_file = Mobileconfig.load(mobileconfig_path)

        return cls(info=info_file, profile=mobileconfig_file)

    def _format_runs_on(self) -> str:
        """Format a profile's runs_on attributes into a human-readable string."""

        all_platforms = ["Mac", "iPhone", "iPad", "TV", "Vision"]

        runs_on_list = [
            platform for platform in all_platforms if getattr(self.info, f"runs_on_{platform.lower()}", False)
        ]

        runs_on_length = len(runs_on_list)

        if runs_on_length == 0:
            runs_on_list = all_platforms.copy()

        if runs_on_length == 1:
            return runs_on_list[0]
        elif runs_on_length == 2:
            return f"{runs_on_list[0]} and {runs_on_list[1]}"
        else:
            return f"{', '.join(runs_on_list[:-1])}, and {runs_on_list[-1]}"

    @override
    @classmethod
    def list_remote(cls, config: ApiConfig) -> PayloadList[CustomProfilePayload]:
        """List custom profiles from Kandji"""
        with CustomProfilesResource(config) as api:
            return api.list()

    @override
    @classmethod
    def get_remote_by_id(cls, config: ApiConfig, id: str) -> CustomProfilePayload:
        """Get custom profile object from Kandji by ID"""
        with CustomProfilesResource(config) as api:
            return api.get(id=id)

    @override
    def get_remote(self, config: ApiConfig) -> CustomProfilePayload:
        """Get custom profile object from Kandji"""
        with CustomProfilesResource(config) as api:
            return api.get(id=self.id)

    @override
    def create_remote(self, config: ApiConfig) -> CustomProfilePayload:
        """Create custom profile object in Kandji"""
        with CustomProfilesResource(config) as api:
            return api.create(
                name=self.name,
                file=self.profile_path,
                active=self.info.active,
                runs_on_mac=self.info.runs_on_mac,
                runs_on_iphone=self.info.runs_on_iphone,
                runs_on_ipad=self.info.runs_on_ipad,
                runs_on_tv=self.info.runs_on_tv,
                runs_on_vision=self.info.runs_on_vision,
            )

    @override
    def update_remote(self, config: ApiConfig) -> CustomProfilePayload:
        """Update custom profile object in Kandji"""
        with CustomProfilesResource(config) as api:
            return api.update(
                id=self.id,
                name=self.name,
                file=self.profile_path,
                active=self.info.active,
                runs_on_mac=self.info.runs_on_mac,
                runs_on_iphone=self.info.runs_on_iphone,
                runs_on_ipad=self.info.runs_on_ipad,
                runs_on_tv=self.info.runs_on_tv,
                runs_on_vision=self.info.runs_on_vision,
            )

    @override
    def delete_remote(self, config: ApiConfig):
        """Delete custom profile object in Kandji"""
        with CustomProfilesResource(config) as api:
            api.delete(id=self.id)

    @override
    def prepare_syntax_dict(self, syntax: SyntaxType | None = None) -> dict:
        """Format the CustomProfile object as a dictionary for output conversion."""

        output_dict = self.info.model_dump(mode="json", exclude={"sync_hash"})
        output_dict["profile"] = self.profile.content
        if output_dict.get("updated_at") is None:
            output_dict["updated_at"] = output_dict["created_at"]

        # do format specific transforms
        match syntax:
            case SyntaxType.XML:
                # To avoid double-encoding, we need to decode the profile content
                output_dict["profile"] = plistlib.loads(output_dict["profile"].encode())
                # Plistlib does not support None values, so we need to remove them
                output_dict = {k: v for k, v in output_dict.items() if v is not None}
                return output_dict
            case SyntaxType.YAML:
                # Use yaml's literal scalar string for better presentation
                output_dict["profile"] = LiteralScalarString(output_dict["profile"])
                return output_dict
            case _:
                return output_dict

    @override
    def format_table(self) -> Table:
        table = Table(
            title=f"Custom Profile Details ({'Local' if self.has_paths else 'Remote'})",
            show_lines=True,
            title_justify="left",
            show_header=False,
        )
        table.add_column("Field", style="bold italic")
        table.add_row("ID", self.id)
        table.add_row("Name", self.name)
        table.add_row("MDM Identifier", self.info.mdm_identifier)
        table.add_row("Active", str(self.info.active))
        table.add_row("Runs On", self._format_runs_on())
        table.add_row("Created At", self.info.created_at)
        table.add_row("Updated At", self.info.updated_at if self.info.updated_at is not None else self.info.created_at)
        table.add_row("Profile", Syntax(self.profile.content, "xml", background_color="default"))

        return table
