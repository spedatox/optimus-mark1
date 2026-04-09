"""
Log and session storage types.
Mirrors src/types/logs.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from optimus.types.ids import AgentId


# ---------------------------------------------------------------------------
# File history / attribution types (referenced by LogOption)
# ---------------------------------------------------------------------------


@dataclass
class FileAttributionState:
    content_hash: str
    claude_contribution: int
    mtime: float


@dataclass
class AttributionSnapshotMessage:
    type: Literal["attribution-snapshot"] = "attribution-snapshot"
    message_id: str = ""
    surface: str = ""
    file_states: dict[str, FileAttributionState] = field(default_factory=dict)
    prompt_count: int | None = None
    prompt_count_at_last_commit: int | None = None
    permission_prompt_count: int | None = None
    permission_prompt_count_at_last_commit: int | None = None
    escape_count: int | None = None
    escape_count_at_last_commit: int | None = None


# ---------------------------------------------------------------------------
# Worktree state
# ---------------------------------------------------------------------------


@dataclass
class PersistedWorktreeSession:
    original_cwd: str
    worktree_path: str
    worktree_name: str
    session_id: str
    worktree_branch: str | None = None
    original_branch: str | None = None
    original_head_commit: str | None = None
    tmux_session_name: str | None = None
    hook_based: bool | None = None


@dataclass
class WorktreeStateEntry:
    type: Literal["worktree-state"] = "worktree-state"
    session_id: str = ""
    worktree_session: PersistedWorktreeSession | None = None


# ---------------------------------------------------------------------------
# Content replacement
# ---------------------------------------------------------------------------


@dataclass
class ContentReplacementRecord:
    """A single content-block replacement decision."""

    block_id: str
    file_path: str
    preview: str


@dataclass
class ContentReplacementEntry:
    type: Literal["content-replacement"] = "content-replacement"
    session_id: str = ""
    agent_id: AgentId | None = None
    replacements: list[ContentReplacementRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LogOption — represents a session in /resume list
# ---------------------------------------------------------------------------


@dataclass
class LogOption:
    date: str
    messages: list[Any]  # SerializedMessage[]
    value: int
    created: datetime
    modified: datetime
    first_prompt: str
    message_count: int
    full_path: str | None = None
    file_size: int | None = None
    is_sidechain: bool = False
    is_lite: bool | None = None
    session_id: str | None = None
    team_name: str | None = None
    agent_name: str | None = None
    agent_color: str | None = None
    agent_setting: str | None = None
    is_teammate: bool | None = None
    leaf_uuid: str | None = None
    summary: str | None = None
    custom_title: str | None = None
    tag: str | None = None
    git_branch: str | None = None
    project_path: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    pr_repository: str | None = None
    mode: Literal["coordinator", "normal"] | None = None


def sort_logs(logs: list[LogOption]) -> list[LogOption]:
    """Sort session logs by modified date (newest first), then created date."""
    return sorted(
        logs,
        key=lambda log: (log.modified.timestamp(), log.created.timestamp()),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# SerializedMessage, TranscriptMessage
# ---------------------------------------------------------------------------


@dataclass
class SerializedMessage:
    """A message serialized to the transcript file."""

    cwd: str
    user_type: str
    session_id: str
    timestamp: str
    version: str
    entrypoint: str | None = None
    git_branch: str | None = None
    slug: str | None = None
    # Plus all Message fields — type, uuid, etc.
    type: str = ""
    uuid: str = ""
    # ... rest of Message fields merged in


@dataclass
class TranscriptMessage(SerializedMessage):
    parent_uuid: str | None = None
    logical_parent_uuid: str | None = None
    is_sidechain: bool = False
    agent_id: str | None = None
    team_name: str | None = None
    agent_name: str | None = None
    agent_color: str | None = None
    prompt_id: str | None = None


# ---------------------------------------------------------------------------
# Metadata messages (append-only transcript entries)
# ---------------------------------------------------------------------------


@dataclass
class SummaryMessage:
    type: Literal["summary"] = "summary"
    leaf_uuid: str = ""
    summary: str = ""


@dataclass
class CustomTitleMessage:
    type: Literal["custom-title"] = "custom-title"
    session_id: str = ""
    custom_title: str = ""


@dataclass
class AiTitleMessage:
    type: Literal["ai-title"] = "ai-title"
    session_id: str = ""
    ai_title: str = ""


@dataclass
class LastPromptMessage:
    type: Literal["last-prompt"] = "last-prompt"
    session_id: str = ""
    last_prompt: str = ""


@dataclass
class TaskSummaryMessage:
    type: Literal["task-summary"] = "task-summary"
    session_id: str = ""
    summary: str = ""
    timestamp: str = ""


@dataclass
class TagMessage:
    type: Literal["tag"] = "tag"
    session_id: str = ""
    tag: str = ""


@dataclass
class AgentNameMessage:
    type: Literal["agent-name"] = "agent-name"
    session_id: str = ""
    agent_name: str = ""


@dataclass
class AgentColorMessage:
    type: Literal["agent-color"] = "agent-color"
    session_id: str = ""
    agent_color: str = ""


@dataclass
class AgentSettingMessage:
    type: Literal["agent-setting"] = "agent-setting"
    session_id: str = ""
    agent_setting: str = ""


@dataclass
class PRLinkMessage:
    type: Literal["pr-link"] = "pr-link"
    session_id: str = ""
    pr_number: int = 0
    pr_url: str = ""
    pr_repository: str = ""
    timestamp: str = ""


@dataclass
class ModeEntry:
    type: Literal["mode"] = "mode"
    session_id: str = ""
    mode: Literal["coordinator", "normal"] = "normal"


@dataclass
class SpeculationAcceptMessage:
    type: Literal["speculation-accept"] = "speculation-accept"
    timestamp: str = ""
    time_saved_ms: float = 0.0


@dataclass
class ContextCollapseCommitEntry:
    type: Literal["marble-origami-commit"] = "marble-origami-commit"
    session_id: str = ""
    collapse_id: str = ""
    summary_uuid: str = ""
    summary_content: str = ""
    summary: str = ""
    first_archived_uuid: str = ""
    last_archived_uuid: str = ""


@dataclass
class ContextCollapseSnapshotEntry:
    type: Literal["marble-origami-snapshot"] = "marble-origami-snapshot"
    session_id: str = ""
    staged: list[dict[str, Any]] = field(default_factory=list)
    armed: bool = False
    last_spawn_tokens: int = 0


@dataclass
class FileHistorySnapshotMessage:
    type: Literal["file-history-snapshot"] = "file-history-snapshot"
    message_id: str = ""
    snapshot: Any = None
    is_snapshot_update: bool = False


# Union of all transcript entry types
Entry = (
    TranscriptMessage
    | SummaryMessage
    | CustomTitleMessage
    | AiTitleMessage
    | LastPromptMessage
    | TaskSummaryMessage
    | TagMessage
    | AgentNameMessage
    | AgentColorMessage
    | AgentSettingMessage
    | PRLinkMessage
    | FileHistorySnapshotMessage
    | AttributionSnapshotMessage
    | SpeculationAcceptMessage
    | ModeEntry
    | WorktreeStateEntry
    | ContentReplacementEntry
    | ContextCollapseCommitEntry
    | ContextCollapseSnapshotEntry
)
