import hashlib
import io
import json
import plistlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict
from rich.table import Table

from kst.api import ApiConfig, ApiPayloadType, PayloadList
from kst.console import OutputFormat, SyntaxType, render_plain_text
from kst.utils import yaml

from .content import File
from .info import InfoFile


class MemberBase[InfoType: InfoFile](BaseModel, ABC):
    """A data model for representing a custom script."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    info: InfoType

    @property
    def id(self) -> str:
        """Get the unique identifier."""
        return self.info.id

    @id.setter
    def id(self, value: str) -> None:
        """Set the unique identifier."""
        self.info.id = value

    @property
    def name(self) -> str:
        """Get the name."""
        return self.info.name

    @name.setter
    def name(self, value: str) -> None:
        """Set the name."""
        self.info.name = value

    @property
    def info_path(self) -> Path:
        """Get the path to the info file."""
        if self.info.path is None:
            raise ValueError("The info_path property must be set before reading.")
        return self.info.path

    @info_path.setter
    def info_path(self, value: Path) -> None:
        """Set the path to the info file."""
        self.info.path = value

    @property
    def children(self) -> list[File | InfoType]:
        """Get the child content objects."""
        return [c for c in (getattr(self, field) for field in type(self).model_fields.keys()) if c is not None]

    @property
    def diff_hash(self) -> str:
        """Get the hash relevant for diff operations."""
        return hashlib.sha256("".join(child.diff_hash for child in self.children).encode()).hexdigest()

    @property
    def sync_hash(self) -> str | None:
        """Get the stored hash at last sync."""
        return self.info.sync_hash

    @sync_hash.setter
    def sync_hash(self, value: str) -> None:
        """Set the stored hash."""
        self.info.sync_hash = value

    def updated(self, other: Self) -> Self:
        """Return an updated object."""

        update_map = {}
        for field in type(self).model_fields.keys():
            self_value = getattr(self, field)
            other_value = getattr(other, field)
            if isinstance(self_value, BaseModel) and isinstance(other_value, BaseModel):
                # Since member objects created from an API response will not have paths and sync_hash attributes
                # set, the update parameter of model copy is passed a dictionary with those values removed. This
                # prevents the local member data from being overwritten with None values.
                update_map[field] = self_value.model_copy(update=other_value.model_dump(exclude={"path", "sync_hash"}))
            else:
                update_map[field] = other_value

        return type(self)(**update_map)

    @property
    def has_paths(self) -> bool:
        """Check if the path properties are set."""
        return all(child.path is not None for child in self.children)

    @abstractmethod
    def ensure_paths(self, repo_path: Path) -> None:
        """Set the path properties to valid default paths within the repository."""

    @abstractmethod
    def write(
        self,
        write_content=True,
    ) -> None:
        """Save the instance to the file system at the path locations."""

    @classmethod
    @abstractmethod
    def from_api_payload(cls, payload: ApiPayloadType) -> Self:
        """Create an instance from an API payload."""

    @abstractmethod
    def to_api_payload(self) -> ApiPayloadType:
        """Convert the instance to an API payload."""

    @classmethod
    @abstractmethod
    def from_path(cls, path: Path, generate: bool = True) -> Self:
        """Load an instance from a file path."""

    def _get_content_by_attribute(self, content_attribute: str) -> str | None:
        """Get the content string by attribute name."""
        try:
            attr = getattr(self, content_attribute)
        except AttributeError:
            raise ValueError(f"Attribute {content_attribute} not found in {self.__class__.__name__}.")
        return attr.content if attr is not None else None

    @classmethod
    @abstractmethod
    def list_remote(cls, config: ApiConfig) -> PayloadList[ApiPayloadType]:
        """List objects from Kandji"""

    @classmethod
    @abstractmethod
    def get_remote_by_id(cls, config: ApiConfig, id: str) -> ApiPayloadType:
        """Get object from Kandji by ID"""

    @abstractmethod
    def get_remote(self, config: ApiConfig) -> ApiPayloadType:
        """Get object from Kandji"""

    @abstractmethod
    def create_remote(self, config: ApiConfig) -> ApiPayloadType:
        """Create object in Kandji"""

    @abstractmethod
    def update_remote(self, config: ApiConfig) -> ApiPayloadType:
        """Update object in Kandji"""

    @abstractmethod
    def delete_remote(self, config: ApiConfig):
        """Delete object in Kandji"""

    @abstractmethod
    def prepare_syntax_dict(self, syntax: SyntaxType | None) -> dict:
        """Format the member object as a string of the provided format."""

    @abstractmethod
    def format_table(self) -> Table:
        """Convert a member into a printable Table."""

    def format_plain_text(self, format: OutputFormat) -> str:
        """Format the script content as syntax-highlighted text."""
        if format == OutputFormat.TABLE:
            return render_plain_text(self.format_table())

        format_dict = self.prepare_syntax_dict(syntax=format.to_syntax())

        match format:
            case OutputFormat.PLIST:
                return plistlib.dumps(format_dict, fmt=plistlib.FMT_XML, sort_keys=False).decode()
            case OutputFormat.JSON:
                return json.dumps(format_dict, indent=2)
            case OutputFormat.YAML:
                output_str = io.StringIO()
                yaml.dump(format_dict, output_str)
                return output_str.getvalue()
