"""
All message types used throughout the agent loop.
Mirrors src/types/message.ts (reconstructed — file missing from archive).

The Message union is the single data structure flowing through:
  query.py → QueryEngine → tools → history → TUI
"""
from __future__ import annotations

import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from optimus.types.ids import AgentId
from optimus.types.permissions import PermissionMode
from optimus.types.tools import ToolProgressData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SystemMessageLevel = Literal["info", "warning", "error"]
MessageOrigin = Literal["human", "hook", "tool", "system"]
PartialCompactDirection = Literal["keep_first", "keep_last"]

# Type variable for generic progress messages
P = TypeVar("P", bound=ToolProgressData)


def _new_uuid() -> str:
    return str(_uuid_mod.uuid4())


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# AssistantMessage
# ---------------------------------------------------------------------------


@dataclass
class AssistantMessageContent:
    """Mirrors the BetaMessage shape from @anthropic-ai/sdk."""

    id: str
    model: str
    role: Literal["assistant"]
    stop_reason: str
    stop_sequence: str | None
    type: Literal["message"]
    content: list[Any]  # ContentBlock[]
    usage: dict[str, Any]
    container: Any | None = None
    context_management: Any | None = None


@dataclass
class AssistantMessage:
    """A message produced by the Claude API."""

    type: Literal["assistant"] = "assistant"
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    message: AssistantMessageContent = field(default_factory=lambda: AssistantMessageContent(
        id=_new_uuid(), model="", role="assistant",
        stop_reason="stop_sequence", stop_sequence=None,
        type="message", content=[], usage={},
    ))
    request_id: str | None = None
    api_error: Any | None = None   # APIError from @anthropic-ai/sdk
    error: Any | None = None       # SDKAssistantMessageError
    error_details: str | None = None
    is_api_error_message: bool = False
    is_virtual: bool | None = None


# ---------------------------------------------------------------------------
# UserMessage
# ---------------------------------------------------------------------------


@dataclass
class UserMessageContent:
    role: Literal["user"]
    content: list[Any] | str  # ContentBlockParam[] | string


@dataclass
class SummarizeMetadata:
    messages_summarized: int
    user_context: str | None = None
    direction: PartialCompactDirection | None = None


@dataclass
class McpMeta:
    meta: dict[str, Any] | None = None
    structured_content: dict[str, Any] | None = None


@dataclass
class UserMessage:
    """A message sent by the user (or synthetically on their behalf)."""

    type: Literal["user"] = "user"
    message: UserMessageContent = field(default_factory=lambda: UserMessageContent(
        role="user", content=""
    ))
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    is_meta: bool | None = None
    is_visible_in_transcript_only: bool | None = None
    is_virtual: bool | None = None
    is_compact_summary: bool | None = None
    summarize_metadata: SummarizeMetadata | None = None
    tool_use_result: Any | None = None
    mcp_meta: McpMeta | None = None
    image_paste_ids: list[int] | None = None
    source_tool_assistant_uuid: str | None = None
    permission_mode: PermissionMode | None = None
    origin: MessageOrigin | None = None


# ---------------------------------------------------------------------------
# ProgressMessage<P>
# ---------------------------------------------------------------------------


@dataclass
class ProgressMessage:
    """
    Carries incremental progress data from a running tool.
    Mirrors ProgressMessage<P> — typed on tool-specific progress data P.
    """

    type: Literal["progress"] = "progress"
    data: Any = None          # ToolProgressData | HookProgress
    tool_use_id: str = ""
    parent_tool_use_id: str = ""
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# AttachmentMessage
# ---------------------------------------------------------------------------


@dataclass
class AttachmentMessage:
    """A message carrying a file/image attachment."""

    type: Literal["attachment"] = "attachment"
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    content: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TombstoneMessage — placeholder for removed messages
# ---------------------------------------------------------------------------


@dataclass
class TombstoneMessage:
    type: Literal["tombstone"] = "tombstone"
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    original_uuid: str = ""


# ---------------------------------------------------------------------------
# System message base fields (shared across all system subtypes)
# ---------------------------------------------------------------------------

_SYSTEM_BASE_FIELDS = ("type", "subtype", "uuid", "timestamp", "is_meta")


@dataclass
class _SystemBase:
    type: Literal["system"] = "system"
    subtype: str = ""
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    is_meta: bool = False


# ---------------------------------------------------------------------------
# Concrete system message variants
# ---------------------------------------------------------------------------


@dataclass
class SystemInformationalMessage(_SystemBase):
    subtype: Literal["informational"] = "informational"
    content: str = ""
    level: SystemMessageLevel = "info"
    tool_use_id: str | None = None
    prevent_continuation: bool | None = None


@dataclass
class SystemLocalCommandMessage(_SystemBase):
    """Output from a locally executed slash command."""

    subtype: Literal["local_command"] = "local_command"
    content: str = ""
    level: SystemMessageLevel = "info"


@dataclass
class SystemAPIErrorMessage(_SystemBase):
    """Displayed when an API call fails and Claude is retrying."""

    subtype: Literal["api_error"] = "api_error"
    level: SystemMessageLevel = "error"
    error: Any | None = None
    cause: Any | None = None
    retry_in_ms: int = 0
    retry_attempt: int = 0
    max_retries: int = 0


@dataclass
class SystemPermissionRetryMessage(_SystemBase):
    subtype: Literal["permission_retry"] = "permission_retry"
    content: str = ""
    commands: list[str] = field(default_factory=list)
    level: SystemMessageLevel = "info"


@dataclass
class SystemBridgeStatusMessage(_SystemBase):
    subtype: Literal["bridge_status"] = "bridge_status"
    content: str = ""
    url: str = ""
    upgrade_nudge: str | None = None


@dataclass
class SystemCompactBoundaryMessage(_SystemBase):
    """Marks the start of a context compaction window."""

    subtype: Literal["compact_boundary"] = "compact_boundary"
    content: str = ""
    level: SystemMessageLevel = "info"
    compact_metadata: dict[str, Any] | None = None
    logical_parent_uuid: str | None = None


@dataclass
class SystemMicrocompactBoundaryMessage(_SystemBase):
    subtype: Literal["microcompact_boundary"] = "microcompact_boundary"
    trigger: Literal["auto"] = "auto"
    pre_tokens: int = 0
    tokens_saved: int = 0
    compacted_tool_ids: list[str] = field(default_factory=list)
    cleared_attachment_uuids: list[str] = field(default_factory=list)


@dataclass
class SystemScheduledTaskFireMessage(_SystemBase):
    subtype: Literal["scheduled_task_fire"] = "scheduled_task_fire"
    content: str = ""


@dataclass
class StopHookInfo:
    hook_name: str
    duration_ms: float
    output: str | None = None


@dataclass
class SystemStopHookSummaryMessage(_SystemBase):
    subtype: Literal["stop_hook_summary"] = "stop_hook_summary"
    hook_count: int = 0
    hook_infos: list[StopHookInfo] = field(default_factory=list)
    hook_errors: list[str] = field(default_factory=list)
    prevented_continuation: bool = False
    stop_reason: str | None = None
    has_output: bool = False
    level: SystemMessageLevel = "info"
    tool_use_id: str | None = None
    hook_label: str | None = None
    total_duration_ms: float | None = None


@dataclass
class SystemTurnDurationMessage(_SystemBase):
    subtype: Literal["turn_duration"] = "turn_duration"
    duration_ms: float = 0.0
    budget_tokens: int | None = None
    budget_limit: int | None = None
    budget_nudges: int | None = None
    message_count: int | None = None


@dataclass
class SystemAwaySummaryMessage(_SystemBase):
    subtype: Literal["away_summary"] = "away_summary"
    content: str = ""


@dataclass
class SystemMemorySavedMessage(_SystemBase):
    subtype: Literal["memory_saved"] = "memory_saved"
    written_paths: list[str] = field(default_factory=list)


@dataclass
class SystemAgentsKilledMessage(_SystemBase):
    subtype: Literal["agents_killed"] = "agents_killed"


@dataclass
class SystemApiMetricsMessage(_SystemBase):
    subtype: Literal["api_metrics"] = "api_metrics"
    ttft_ms: float = 0.0
    otps: float = 0.0
    is_p50: bool | None = None
    hook_duration_ms: float | None = None
    turn_duration_ms: float | None = None
    tool_duration_ms: float | None = None
    classifier_duration_ms: float | None = None
    tool_count: int | None = None
    hook_count: int | None = None
    classifier_count: int | None = None
    config_write_count: int | None = None


@dataclass
class SystemBridgeStatusMessage(_SystemBase):  # type: ignore[no-redef]
    subtype: Literal["bridge_status"] = "bridge_status"
    content: str = ""
    url: str = ""
    upgrade_nudge: str | None = None


# Union of all system message variants
SystemMessage = (
    SystemInformationalMessage
    | SystemLocalCommandMessage
    | SystemAPIErrorMessage
    | SystemPermissionRetryMessage
    | SystemBridgeStatusMessage
    | SystemCompactBoundaryMessage
    | SystemMicrocompactBoundaryMessage
    | SystemScheduledTaskFireMessage
    | SystemStopHookSummaryMessage
    | SystemTurnDurationMessage
    | SystemAwaySummaryMessage
    | SystemMemorySavedMessage
    | SystemAgentsKilledMessage
    | SystemApiMetricsMessage
)

# ---------------------------------------------------------------------------
# HookResultMessage — from hook execution (mirrors types/message.ts usage)
# ---------------------------------------------------------------------------


@dataclass
class HookResultMessage:
    """A message injected by a hook's output."""

    type: Literal["hook_result"] = "hook_result"
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    content: str = ""
    source: str = ""  # hook name
    is_error: bool = False


# ---------------------------------------------------------------------------
# ToolUseSummaryMessage
# ---------------------------------------------------------------------------


@dataclass
class ToolUseSummaryMessage:
    type: Literal["tool_use_summary"] = "tool_use_summary"
    uuid: str = field(default_factory=_new_uuid)
    timestamp: str = field(default_factory=_now_iso)
    tool_name: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# StreamEvent, RequestStartEvent
# ---------------------------------------------------------------------------


@dataclass
class RequestStartEvent:
    type: Literal["request_start"] = "request_start"
    request_id: str = ""
    timestamp: str = field(default_factory=_now_iso)


StreamEvent = Any  # SDK streaming events — mapped to anthropic SDK stream events


# ---------------------------------------------------------------------------
# NormalizedMessage variants
# (same shape as regular messages but guaranteed not to be system/progress)
# ---------------------------------------------------------------------------

NormalizedAssistantMessage = AssistantMessage  # alias — all fields present
NormalizedUserMessage = UserMessage            # alias — all fields present
NormalizedMessage = AssistantMessage | UserMessage

# ---------------------------------------------------------------------------
# Top-level Message union
# ---------------------------------------------------------------------------

Message = (
    AssistantMessage
    | UserMessage
    | ProgressMessage
    | AttachmentMessage
    | TombstoneMessage
    | HookResultMessage
    | ToolUseSummaryMessage
    | SystemInformationalMessage
    | SystemLocalCommandMessage
    | SystemAPIErrorMessage
    | SystemPermissionRetryMessage
    | SystemBridgeStatusMessage
    | SystemCompactBoundaryMessage
    | SystemMicrocompactBoundaryMessage
    | SystemScheduledTaskFireMessage
    | SystemStopHookSummaryMessage
    | SystemTurnDurationMessage
    | SystemAwaySummaryMessage
    | SystemMemorySavedMessage
    | SystemAgentsKilledMessage
    | SystemApiMetricsMessage
)

# RenderableMessage — subset of messages that can render in the TUI
RenderableMessage = (
    AssistantMessage
    | UserMessage
    | SystemInformationalMessage
    | SystemLocalCommandMessage
    | SystemAPIErrorMessage
    | ProgressMessage
    | HookResultMessage
    | ToolUseSummaryMessage
)
