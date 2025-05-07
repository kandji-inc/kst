import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

import typer

from kst.console import OutputConsole, OutputFormat, SyntaxType
from kst.diff import ChangeType
from kst.repository import MemberBase

console = OutputConsole(logging.getLogger(__name__))

# --- Shared Options ---
# General Options Panel
RepoPathOption = Annotated[
    str,
    typer.Option(
        "--repo",
        help="Path to the local repository.",
        metavar="DIRECTORY",
        show_default=False,
    ),
]
FormatOption = Annotated[
    OutputFormat,
    typer.Option(
        "--format",
        "-f",
        help="Format to use for output.",
    ),
]
OutputOption = Annotated[
    str,
    typer.Option(
        "--output",
        "-o",
        allow_dash=True,
        show_default="stdout",
        help="Output file",
    ),
]
DryRunOption = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        "-n",
        help="Perform a dry run without making changes.",
        show_default=False,
    ),
]
ForceOption = Annotated[
    bool,
    typer.Option(
        "--force",
        help="Overwrite instead of reporting conflicts.",
    ),
]

# Kandji Info Panel
KandjiTenantOption = Annotated[
    str | None,
    typer.Option(
        "--tenant-url",
        "-u",
        show_default=False,
        envvar="KST_TENANT",
        rich_help_panel="Kandji Info",
        help="Kandji tenant URL",
    ),
]
ApiTokenOption = Annotated[
    str | None,
    typer.Option(
        "--api-token",
        "-t",
        show_default=False,
        envvar="KST_TOKEN",
        rich_help_panel="Kandji Info",
        help="Kandji API token",
    ),
]

# Filters Panel
IncludeOption = Annotated[
    list[ChangeType],
    typer.Option(
        "--include",
        "-i",
        show_default=False,
        rich_help_panel="Filters",
        help="Include a specific change type in the output.",
    ),
]
ExcludeOption = Annotated[
    list[ChangeType],
    typer.Option(
        "--exclude",
        "-e",
        show_default=False,
        rich_help_panel="Filters",
        help="Exclude a specific change type from the output.",
    ),
]


# --- Shared Data Objects ---
class ForceMode(StrEnum):
    PUSH = "push"
    PULL = "pull"
    SKIP = "skip"


class ActionType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"

    def past_tense(self) -> str:
        """Get the past tense of the action type."""
        match self:
            case ActionType.CREATE:
                return "created"
            case ActionType.UPDATE:
                return "updated"
            case ActionType.DELETE:
                return "deleted"
            case ActionType.SKIP:
                return "skipped"


class OperationType(StrEnum):
    PUSH = "push"
    PULL = "pull"
    SKIP = "skip"


class ResultType(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class PreparedAction[MemberType: MemberBase]:
    """An api action to be performed."""

    action: ActionType
    operation: OperationType
    change: ChangeType
    member: MemberType


@dataclass
class ActionResponse[MemberType: MemberBase]:
    """The response from an api action."""

    id: str  # The original ID of the member since it may change on create actions
    action: ActionType
    operation: OperationType
    result: ResultType
    member: MemberType | None


@dataclass
class SyncResults[MemberType: MemberBase]:
    """The results of a sync operation."""

    success: list[ActionResponse[MemberType]] = field(default_factory=list)
    failure: list[ActionResponse[MemberType]] = field(default_factory=list)
    skipped: list[ActionResponse[MemberType]] = field(default_factory=list)

    def format_summary(self) -> str:
        """Format the summary of the results."""

        success_count = len(self.success)
        failure_count = len(self.failure)
        skipped_count = len(self.skipped)

        summary = ""

        if success_count > 0:
            summary += f"\n\nSuccess ({success_count})"
            for success in self.success:
                summary += f"\n- {success.action.capitalize()} {success.member.name + ' ' if success.member else ''}{success.id} {'in repository' if success.operation is OperationType.PULL else 'in Kandji'}"

        if failure_count > 0:
            summary += f"\n\nFailure ({failure_count})"
            for failure in self.failure:
                summary += f"\n- {failure.action.capitalize()} {failure.member.name + ' ' if failure.member else ''}{failure.id} {'in repository' if failure.operation is OperationType.PULL else 'in Kandji'}"

        if skipped_count > 0:
            summary += f"\n\nSkipped ({skipped_count})"
            for skipped in self.skipped:
                summary += f"\n- {skipped.action.capitalize()} {skipped.member.name + ' ' if skipped.member else ''}{skipped.id} "

        return summary.lstrip()

    def format_report(self) -> dict:
        """Format the results for display."""

        return {
            "id": str(uuid4()),
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "summary": self.format_summary(),
            "status": "failure" if len(self.failure) != 0 else "warning" if len(self.skipped) != 0 else "success",
            "success": [
                {
                    "id": success.id,
                    "action": success.action,
                    "location": "local" if success.operation is OperationType.PULL else "remote",
                    "object": success.member.prepare_syntax_dict(syntax=SyntaxType.JSON) if success.member else None,
                }
                for success in self.success
            ],
            "failure": [
                {
                    "id": failure.id,
                    "action": failure.action,
                    "location": "local" if failure.operation is OperationType.PULL else "remote",
                    "object": failure.member.prepare_syntax_dict(syntax=SyntaxType.JSON) if failure.member else None,
                }
                for failure in self.failure
            ],
            "skipped": [
                {
                    "id": skipped.id,
                    "action": skipped.action,
                    "location": None,
                    "object": skipped.member.prepare_syntax_dict(syntax=SyntaxType.JSON) if skipped.member else None,
                }
                for skipped in self.skipped
            ],
        }
