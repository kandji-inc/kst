import contextlib
import functools
from pathlib import Path
from typing import Self, override
from uuid import UUID

from pygments.lexers import guess_lexer
from rich.syntax import Syntax
from rich.table import Table
from ruamel.yaml.scalarstring import LiteralScalarString

from kst import git
from kst.api import (
    ApiConfig,
    CustomScriptPayload,
    CustomScriptsResource,
    ExecutionFrequency,
    PayloadList,
    SelfServiceCategoriesResource,
)
from kst.console import SyntaxType
from kst.exceptions import (
    DuplicateInfoFileError,
    DuplicateScriptError,
    InvalidScriptError,
    MissingInfoFileError,
    MissingScriptError,
)
from kst.utils import sanitize_filename

from .content import DEFAULT_SCRIPT_CONTENT, DEFAULT_SCRIPT_SUFFIX, Script
from .info import ACCEPTED_INFO_EXTENSIONS, DEFAULT_SCRIPT_CATEGORY, ScriptInfoFile
from .member_base import MemberBase

DIRECTORY_NAME = "scripts"


@functools.cache
def get_category_id(config: ApiConfig, name: str | None = None) -> str:
    """Get the ID for the named category (or default) in Self Service, if it exists."""
    if name is not None:
        with contextlib.suppress(ValueError):
            UUID(name, version=4)
            return name  # name is already a valid UUID

    with SelfServiceCategoriesResource(config) as ss:
        categories = ss.list()

    name = DEFAULT_SCRIPT_CATEGORY if name is None else name
    try:
        return next(c.id for c in categories if c.name.lower() == name.lower())
    except StopIteration:
        raise ValueError(f"Unable to get ID for category '{name}'. Ensure the category exists.")


class CustomScript(MemberBase):
    """A data model for representing a custom script."""

    info: ScriptInfoFile
    audit: Script
    remediation: Script | None = None

    @property
    def audit_path(self) -> Path:
        """Get the path to the remediation script file."""
        if self.audit.path is None:
            raise ValueError("The audit_path property must be set before reading.")
        return self.audit.path

    @audit_path.setter
    def audit_path(self, value: Path) -> None:
        """Set the path to the remediation script file."""
        self.audit.path = value

    @property
    def remediation_path(self) -> Path:
        """Get the path to the remediation script file."""
        if self.remediation is None or self.remediation.path is None:
            raise ValueError("The remediation_path property must be set before reading.")
        return self.remediation.path

    @remediation_path.setter
    def remediation_path(self, value: Path) -> None:
        """Set the path to the remediation script file."""
        if self.remediation is None:
            raise ValueError("The remediation script must exist before its path can be set.")
        self.remediation.path = value

    @property
    def has_remediation(self) -> bool:
        """Check if the remediation script is set."""
        return self.remediation is not None

    @property
    def _formatted_execution_frequency(self) -> str:
        """Format the execution frequency for display."""
        match self.info.execution_frequency:
            case ExecutionFrequency.ONCE:
                return "Once"
            case ExecutionFrequency.EVERY_15_MIN:
                return "Every 15 minutes"
            case ExecutionFrequency.EVERY_DAY:
                return "Every day"
            case ExecutionFrequency.NO_ENFORCEMENT:
                return "No enforcement"

    @override
    def ensure_paths(self, repo_path: Path) -> None:
        """Set the path properties to valid default paths within the repository.

        Raises:
            InvalidRepositoryError: repo_path is not a valid Kandji Sync Toolkit repository.
        """
        if self.has_paths:
            return  # Nothing to do here

        if self.info.path is None:
            repo_path = repo_path.resolve()
            scripts_root = git.locate_root(cd_path=repo_path) / "scripts"

            script_parent = (repo_path if repo_path.is_relative_to(scripts_root) else scripts_root) / sanitize_filename(
                self.info.name
            )

            # If output path already exists, increment the path with a number
            count = 0
            while script_parent.exists():
                count += 1
                script_parent = script_parent.parent / f"{sanitize_filename(self.info.name)} ({count})"

            self.info.path = script_parent / f"info.{self.info.format}"

        if self.audit.path is None:
            self.audit.path = self.info.path.parent / "audit"
        elif self.audit.path.parent != self.info.path.parent:
            self.audit.path = self.info.path.parent / self.audit.path.name

        if self.remediation is not None:
            if self.remediation.path is None:
                self.remediation.path = self.info.path.parent / "remediation"
            elif self.remediation.path.parent != self.info.path.parent:
                self.remediation.path = self.info.path.parent / self.remediation.path.name

    @override
    def write(self, write_content=True) -> None:
        """Save the CustomScript object to the file system."""
        # Ensure valid paths are set
        if not self.has_paths:
            raise ValueError("All path properties must be set before writing the custom script.")

        # Verify that all paths are in the same directory
        all_paths = {str(c.path.parent) for c in self.children if c.path is not None}
        if len(all_paths) != 1:
            raise InvalidScriptError(
                f"All path properties must be paths to files within the same directory ({' != '.join(all_paths)})."
            )

        if self.info_path.stem != "info" or self.info_path.suffix not in ACCEPTED_INFO_EXTENSIONS:
            raise InvalidScriptError(
                "The info_path property must be a path to an info file. Expected format: info.<plist|json|yml|yaml>"
            )

        if not self.audit_path.stem.startswith("audit"):
            raise InvalidScriptError(f'The audit script file name must start with "audit"(got {self.audit_path.name}).')

        if self.has_remediation and not self.remediation_path.stem.startswith("remediation"):
            raise InvalidScriptError(
                f'The remediation script file name must start with "remediation" (got {self.remediation_path.name}).'
            )

        # Create missing directories if they do not exist
        self.info_path.parent.mkdir(parents=True, exist_ok=True)

        # Write info to file
        self.info.write()

        # Write script content to file(s)
        if write_content:
            self.audit.write()
            if self.remediation is None:
                try:
                    remediation_path = next(self.info_path.parent.glob("remediation*"))
                    remediation_path.unlink()
                except StopIteration:
                    pass
            else:
                self.remediation.write()

    @override
    @classmethod
    def from_api_payload(cls, payload: CustomScriptPayload) -> Self:
        """Create a CustomScript object from an API payload."""

        info_file = ScriptInfoFile.model_validate(payload.model_dump(exclude={"script", "remediation_script"}))
        audit_script = Script(content=payload.script)
        if payload.remediation_script != "":
            remediation_script = Script(content=payload.remediation_script)
        else:
            remediation_script = None

        return cls(info=info_file, audit=audit_script, remediation=remediation_script)

    @override
    def to_api_payload(self) -> CustomScriptPayload:
        """Convert to a CustomScriptPayload object."""

        script_dict = self.info.model_dump(exclude={"sync_hash"}) | {
            "script": self.audit.content,
            "remediation_script": self.remediation.content if self.remediation else "",
        }
        if script_dict["updated_at"] is None:
            script_dict["updated_at"] = self.info.created_at

        return CustomScriptPayload.model_validate(script_dict)

    @override
    @classmethod
    def from_path(cls, path: Path, generate: bool = True) -> Self:
        """Load a CustomScript object from a file path.

        The path can be the path to an info file or a directory containing the info and script files.
        """

        # Set the script directory path which will contain the info and mobileconfig files
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

        # Locate audit script and ensure there are no duplicates
        audit_path = list(parent_path.glob("audit*"))
        if len(audit_path) == 0:
            if generate:
                # Create a new audit script with default content
                audit_path = [parent_path / f"audit{DEFAULT_SCRIPT_SUFFIX}"]
                audit_path[0].write_text(DEFAULT_SCRIPT_CONTENT)
            else:
                raise MissingScriptError(
                    f'Unable to locate audit script at {parent_path}. The audit script filename must start with "audit".'
                )
        elif len(audit_path) > 1:
            raise DuplicateScriptError(
                f'Multiple audit scripts exist at {parent_path}. Ensure only one file exits whose filename starts with "audit".\n* {"\n* ".join(str(p for p in audit_path))}'
            )
        audit_path = audit_path[0].resolve()

        # Locate remediation script and ensure there are no duplicates
        remediation_path = list(parent_path.glob("remediation*"))
        if len(remediation_path) > 1:
            raise DuplicateScriptError(
                f'Multiple remediation scripts exist at {parent_path}. Ensure only one file exits whose filename starts with "remediation".\n* {"\n* ".join(str(p for p in remediation_path))}'
            )
        remediation_path = remediation_path[0].resolve() if remediation_path else None

        # Load the info file
        info_file = ScriptInfoFile.load(info_path)

        # Load the audit script and ensure it is not empty
        audit_script = Script.load(audit_path)
        if audit_script.content == "":
            raise InvalidScriptError(
                f'The audit script file "{audit_path.name}" is empty. Please provide a valid script.'
            )

        # Load the remediation script if it exists and ensure it is not empty
        if remediation_path is not None:
            remediation_script = Script.load(remediation_path)
            if remediation_script.content == "":
                # Sending empty content to the API will remove the remediation script
                remediation_script = None
        else:
            remediation_script = None

        return cls(info=info_file, audit=audit_script, remediation=remediation_script)

    @override
    @classmethod
    def list_remote(cls, config: ApiConfig) -> PayloadList[CustomScriptPayload]:
        """List custom script objects from Kandji"""
        with CustomScriptsResource(config) as api:
            return api.list()

    @override
    @classmethod
    def get_remote_by_id(cls, config: ApiConfig, id: str) -> CustomScriptPayload:
        """Get custom script object from Kandji by ID"""
        with CustomScriptsResource(config) as api:
            return api.get(id=id)

    @override
    def get_remote(self, config: ApiConfig) -> CustomScriptPayload:
        """Get custom script object from Kandji"""
        with CustomScriptsResource(config) as api:
            return api.get(id=self.id)

    @override
    def create_remote(self, config: ApiConfig) -> CustomScriptPayload:
        """Create custom script object in Kandji"""
        payload = {
            "name": self.name,
            "script": self.audit.content,
            "remediation_script": "" if self.remediation is None else self.remediation.content,
            "active": self.info.active,
            "execution_frequency": self.info.execution_frequency,
            "restart": self.info.restart,
            "show_in_self_service": self.info.show_in_self_service,
        }
        if self.info.show_in_self_service:
            payload |= {
                "self_service_category_id": get_category_id(config=config, name=self.info.self_service_category_id),
                "self_service_recommended": self.info.self_service_recommended or False,
            }
        with CustomScriptsResource(config) as api:
            return api.create(**payload)

    @override
    def update_remote(self, config: ApiConfig) -> CustomScriptPayload:
        """Update custom script object in Kandji"""
        payload = {
            "id": self.id,
            "name": self.name,
            "script": self.audit.content,
            "remediation_script": "" if self.remediation is None else self.remediation.content,
            "active": self.info.active,
            "execution_frequency": self.info.execution_frequency,
            "restart": self.info.restart,
            "show_in_self_service": self.info.show_in_self_service,
        }
        if self.info.show_in_self_service:
            payload |= {
                "self_service_category_id": get_category_id(config=config, name=self.info.self_service_category_id),
                "self_service_recommended": self.info.self_service_recommended or False,
            }
        with CustomScriptsResource(config) as api:
            return api.update(**payload)

    @override
    def delete_remote(self, config: ApiConfig):
        """Delete custom script object in Kandji"""
        with CustomScriptsResource(config) as api:
            api.delete(id=self.id)

    @override
    def prepare_syntax_dict(self, syntax: SyntaxType | None = None) -> dict:
        """Format the CustomScript object as a dictionary for format conversion."""

        output_dict = self.info.model_dump(mode="json", exclude={"sync_hash"})
        output_dict["audit_script"] = self._get_content_by_attribute("audit")
        output_dict["remediation_script"] = self._get_content_by_attribute("remediation")
        if output_dict.get("updated_at") is None:
            output_dict["updated_at"] = output_dict["created_at"]

        match syntax:
            case SyntaxType.XML:
                # Plist does not support None values, so we need to remove them
                return {k: v for k, v in output_dict.items() if v is not None}
            case SyntaxType.YAML:
                if output_dict["audit_script"] is not None and len(output_dict["audit_script"].splitlines()) > 1:
                    # Use yaml's literal scalar string for better presentation
                    output_dict["audit_script"] = LiteralScalarString(output_dict["audit_script"])
                if (
                    output_dict["remediation_script"] is not None
                    and len(output_dict["remediation_script"].splitlines()) > 1
                ):
                    # Use LiteralScalarString for remediation script to preserve formatting
                    output_dict["remediation_script"] = LiteralScalarString(output_dict["remediation_script"])
                return output_dict
            case _:
                return output_dict

    @override
    def format_table(self) -> Table:
        table = Table(
            title=f"Custom Script Details ({'Local' if self.has_paths else 'Remote'})",
            show_lines=True,
            title_justify="left",
            show_header=False,
        )
        table.add_column("Field", style="bold italic")
        table.add_row("ID", self.id)
        table.add_row("Name", self.name)
        table.add_row("Active", str(self.info.active))
        table.add_row("Execution Frequency", self._formatted_execution_frequency)
        table.add_row("Restart", str(self.info.restart))
        table.add_row("Show in Self Service", str(self.info.show_in_self_service))
        table.add_row("Self Service Category ID", str(self.info.self_service_category_id or ""))
        table.add_row(
            "Self Service Recommended",
            str("" if self.info.self_service_recommended is None else self.info.self_service_recommended),
        )
        table.add_row("Created At", self.info.created_at)
        table.add_row("Updated At", self.info.updated_at if self.info.updated_at is not None else self.info.created_at)
        table.add_row(
            "Audit Script",
            Syntax(self.audit.content, guess_lexer(self.audit.content), background_color="default"),
        )
        remediation_content = self.remediation.content if self.remediation is not None else ""
        table.add_row(
            "Remediation Script",
            Syntax(remediation_content, guess_lexer(remediation_content), background_color="default"),
        )

        return table
