import hashlib
import io
import json
import plistlib
from abc import ABC
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Self, override
from uuid import uuid4
from xml.parsers import expat

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kst.console import OutputFormat
from kst.exceptions import InvalidProfileError
from kst.utils import yaml

DEFAULT_SCRIPT_CONTENT = """#!/bin/zsh -f
# https://support.kandji.io/kb/custom-scripts-overview

echo "Hello, World!"
exit 0
"""
DEFAULT_SCRIPT_SUFFIX = ".zsh"


class File(BaseModel, ABC):
    """An abstract data model for representing a generic file."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    content: str
    path: Path | None = Field(exclude=True, default=None)

    @field_validator("path", mode="after")
    @classmethod
    def ensure_absolute_paths(cls, v: Path | None) -> Path | None:
        """Ensure that the path property is an absolute paths."""
        if isinstance(v, Path):
            v = v.resolve()
        return v

    @property
    def diff_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls(content=path.read_text(), path=path)

    def write(self):
        if self.path is None:
            raise ValueError("Cannot write without a path set.")
        self.path.write_text(self.content)

    def format_plain_text(self, format: OutputFormat) -> str:  # noqa: ARG002
        """Format the content as plain text."""
        return self.content


class Mobileconfig(File):
    """A data model for representing a mobileconfig file."""

    @field_validator("path", mode="after")
    @classmethod
    def ensure_valid_extension(cls, v: Path | None) -> Path | None:
        """Ensure that the path property has a valid extension."""
        if v is not None and v.suffix != ".mobileconfig":
            raise ValueError("Invalid mobileconfig file extension: Expected .mobileconfig")
        return v

    @property
    def data(self) -> dict[str, Any]:
        return self._data(self.content)

    @staticmethod
    @lru_cache
    def _data(content: str | bytes) -> dict[str, Any]:
        try:
            return plistlib.loads(content, dict_type=OrderedDict)
        except (plistlib.InvalidFileException, expat.ExpatError) as error:
            raise ValueError("The mobileconfig content is not a valid plist") from error

    @classmethod
    def default_content(cls, _id: str | None = None, name: str = "New Profile") -> str:
        """Get the default content for a profile."""
        if _id is None:
            _id = str(uuid4())

        return (
            plistlib.dumps(
                {
                    "PayloadDisplayName": name,
                    "PayloadIdentifier": f"com.kandji.profile.custom.{_id}",
                    "PayloadType": "Configuration",
                    "PayloadUUID": _id,
                    "PayloadVersion": 1,
                    "PayloadContent": [{}],
                }
            )
            .decode()
            .expandtabs(4)
        )

    @override
    @classmethod
    def load(cls, path: Path) -> Self:
        profile_bytes = path.read_bytes()
        try:
            profile_data = cls._data(profile_bytes)
        except ValueError as error:
            raise InvalidProfileError(
                f"The mobileconfig at {path} is in an invalid format. Check the file and try again."
            ) from error
        if profile_bytes[:8] == b"bplist00":
            profile_content = plistlib.dumps(profile_data, fmt=plistlib.FMT_XML).decode()
        else:
            profile_content = profile_bytes.decode()
        return cls(content=profile_content, path=path)

    @override
    def format_plain_text(self, format: OutputFormat) -> str:
        format_dict = plistlib.loads(self.content)
        match format:
            case OutputFormat.PLIST | OutputFormat.TABLE:
                return plistlib.dumps(format_dict, fmt=plistlib.FMT_XML, sort_keys=False).decode()
            case OutputFormat.JSON:
                return json.dumps(format_dict, indent=2)
            case OutputFormat.YAML:
                output_str = io.StringIO()
                yaml.dump(format_dict, output_str)
                return output_str.getvalue()


class Script(File):
    """A data model for representing a script file."""

    @override
    def write(self):
        if self.path is None:
            raise ValueError("Cannot write without a path set.")
        self.path.write_text(self.content)

        # Make the script executable
        self.path.chmod(self.path.stat().st_mode | 0o111)
