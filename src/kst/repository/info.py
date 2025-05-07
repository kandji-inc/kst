import hashlib
import json
import plistlib
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self, override
from xml.parsers import expat

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from ruamel.yaml import YAMLError

from kst.api import ExecutionFrequency
from kst.exceptions import InvalidInfoFileError
from kst.utils import yaml

INFO_FORMAT_HASH_KEYS = ("id", "name", "active")
PROFILE_RUNS_ON_PARAMS = ("runs_on_mac", "runs_on_iphone", "runs_on_ipad", "runs_on_tv", "runs_on_vision")
PROFILE_INFO_HASH_KEYS = (*INFO_FORMAT_HASH_KEYS, *PROFILE_RUNS_ON_PARAMS)
SCRIPT_INFO_HASH_KEYS = (
    *INFO_FORMAT_HASH_KEYS,
    "execution_frequency",
    "restart",
    "show_in_self_service",
    "self_service_category_id",
    "self_service_recommended",
)
DEFAULT_SCRIPT_CATEGORY = "Utilities"


class InfoFormat(StrEnum):
    PLIST = "plist"
    JSON = "json"
    YAML = "yaml"


SUFFIX_MAP = OrderedDict(
    [
        (".plist", InfoFormat.PLIST),
        (".json", InfoFormat.JSON),
        (".yaml", InfoFormat.YAML),
        (".yml", InfoFormat.YAML),
    ]
)
ACCEPTED_INFO_EXTENSIONS = set(SUFFIX_MAP.keys())
INFO_FORMAT = f"info.<{'|'.join(SUFFIX_MAP.keys())}>"


class InfoFile(BaseModel, ABC):
    """An abstract data model for representing a generic info file."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: Annotated[str, AfterValidator(lambda value: value.lower())]
    name: str
    active: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    updated_at: str | None = None
    sync_hash: str | None = None
    format: InfoFormat = Field(exclude=True, default=InfoFormat.PLIST)
    path: Path | None = Field(exclude=True, default=None)

    @field_validator("path", mode="after")
    @classmethod
    def ensure_absolute_paths(cls, v: Path | None) -> Path | None:
        """Ensure that the path property is an absolute paths."""
        if isinstance(v, Path):
            v = v.resolve()
        return v

    @field_validator("path", mode="after")
    @classmethod
    def ensure_valid_file_name(cls, v: Path | None) -> Path | None:
        """Ensure that the path property is a valid file name."""
        if isinstance(v, Path):
            if v.stem != "info" or v.suffix not in ACCEPTED_INFO_EXTENSIONS:
                raise ValueError("Invalid info file name. Expected format: {INFO_FORMAT}")
        return v

    @classmethod
    def load(cls, path: Path) -> Self:
        match path.suffix:
            case ".plist":
                with path.open("rb") as file:
                    try:  # Load plist data
                        info_data = plistlib.load(file)
                    except (plistlib.InvalidFileException, expat.ExpatError) as error:
                        raise InvalidInfoFileError(
                            f"Profile info at {path} is not a valid plist file.\n{error}"
                        ) from error
            case ".json":
                with path.open("r") as file:
                    try:
                        info_data = json.load(file)
                    except json.JSONDecodeError as error:
                        raise InvalidInfoFileError(
                            f"Profile info at {path} is not a valid json file.\n{error}"
                        ) from error
            case ".yml" | ".yaml":
                try:
                    info_data = yaml.load(path)
                except YAMLError as error:
                    raise InvalidInfoFileError(f"Profile info at {path} is not a valid yaml file.\n{error}") from error
            case _:
                raise InvalidInfoFileError(f"Profile info file at {path} does not have a valid suffix. ({INFO_FORMAT})")

        info_data["path"] = path
        info_data["format"] = SUFFIX_MAP[path.suffix]
        try:
            return cls.model_validate(info_data)
        except ValidationError as error:
            raise InvalidInfoFileError(f"Profile info at {path} is not a valid info file.\n{error}") from error

    def write(self) -> None:
        if self.path is None:
            raise ValueError("The info file has no path set.")

        # Ensure all values are json serializable to be compatible with write formats
        # Exclude any unset values to avoid writing defaults
        # Exclude any None values to minimize unnecessary data
        # Exclude profile and info_path since they are unnecessary in the info file
        info_data = self.model_dump(mode="json", exclude_unset=True, exclude_none=True, exclude={"path", "content"})

        # Create missing directories if they do not exist
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Write info to file
        if self.path.suffix == ".plist":
            with self.path.open("wb") as file:
                # plistlib dump's indent type is not configurable. As a workaround, we dump to a string and use expandtabs.
                plist_str = plistlib.dumps(info_data, sort_keys=False)
                file.write(plist_str.expandtabs(4))
        elif self.path.suffix == ".json":
            with self.path.open("w") as file:
                json.dump(info_data, file, indent=2)
        elif self.path.suffix in (".yml", ".yaml"):
            with self.path.open("w") as file:
                yaml.dump(info_data, file)

    @property
    @abstractmethod
    def diff_hash(self) -> str: ...


class ProfileInfoFile(InfoFile):
    """A data model for representing a profile info file."""

    mdm_identifier: str = ""
    runs_on_mac: bool = False
    runs_on_iphone: bool = False
    runs_on_ipad: bool = False
    runs_on_tv: bool = False
    runs_on_vision: bool = False

    @model_validator(mode="after")
    def ensure_mdm_identifier(self) -> Self:
        """Ensure the MDM identifier is set."""
        if self.mdm_identifier == "":
            self.mdm_identifier = f"com.kandji.profile.custom.{self.id}"
        return self

    @model_validator(mode="after")
    def at_least_one_runs_on(self) -> Self:
        """Ensure at least one runs_on_* is True."""

        if not set(PROFILE_RUNS_ON_PARAMS).intersection(self.model_fields_set):
            for param in PROFILE_RUNS_ON_PARAMS:
                setattr(self, param, True)

        if not any(getattr(self, param) for param in PROFILE_RUNS_ON_PARAMS):
            raise ValueError("At least one runs_on_* property must be True.")
        return self

    @property
    @override
    def diff_hash(self) -> str:
        diff_dict = self.model_dump(include=set(PROFILE_INFO_HASH_KEYS))
        for param in PROFILE_RUNS_ON_PARAMS:
            if diff_dict[param] is None:
                diff_dict[param] = False

        # manually joining data to string is required to ensure consistent key order
        return hashlib.sha256("".join(str(diff_dict.get(key)) for key in PROFILE_INFO_HASH_KEYS).encode()).hexdigest()


class ScriptInfoFile(InfoFile):
    """A data model for representing a script info file."""

    execution_frequency: ExecutionFrequency = ExecutionFrequency.ONCE
    restart: bool = False
    show_in_self_service: bool = False
    self_service_category_id: str | None = None
    self_service_recommended: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def update_self_service_options(cls, values: Any) -> Any:
        """Set default show in self service options."""
        if isinstance(values, dict) and (
            values.get("show_in_self_service") is True
            or values.get("self_service_recommended") is True
            or values.get("self_service_category_id") is not None
            or values.get("execution_frequency") == ExecutionFrequency.NO_ENFORCEMENT
        ):
            # Set default values for missing self service options if any are provided
            values["show_in_self_service"] = True
            values["self_service_category_id"] = values.get("self_service_category_id") or DEFAULT_SCRIPT_CATEGORY
            values["self_service_recommended"] = values.get("self_service_recommended") or False
        return values

    @property
    @override
    def diff_hash(self) -> str:
        diff_dict = self.model_dump(include=set(SCRIPT_INFO_HASH_KEYS))
        # manually joining data to string is required to ensure consistent key order
        return hashlib.sha256("".join(str(diff_dict.get(key)) for key in SCRIPT_INFO_HASH_KEYS).encode()).hexdigest()
