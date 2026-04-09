"""
Hook-related types.
Mirrors src/types/hooks.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# Prompt elicitation
# ---------------------------------------------------------------------------


@dataclass
class PromptOption:
    key: str
    label: str
    description: str | None = None


@dataclass
class PromptRequest:
    prompt: str  # request id
    message: str
    options: list[PromptOption] = field(default_factory=list)


@dataclass
class PromptResponse:
    prompt_response: str  # request id
    selected: str


# ---------------------------------------------------------------------------
# Sync hook response
# ---------------------------------------------------------------------------


@dataclass
class PreToolUseHookOutput:
    hook_event_name: Literal["PreToolUse"] = "PreToolUse"
    permission_decision: Literal["approve", "block"] | None = None
    permission_decision_reason: str | None = None
    updated_input: dict[str, Any] | None = None
    additional_context: str | None = None


@dataclass
class PostToolUseHookOutput:
    hook_event_name: Literal["PostToolUse"] = "PostToolUse"
    additional_context: str | None = None
    updated_mcp_tool_output: Any | None = None


@dataclass
class SessionStartHookOutput:
    hook_event_name: Literal["SessionStart"] = "SessionStart"
    additional_context: str | None = None
    initial_user_message: str | None = None
    watch_paths: list[str] | None = None


@dataclass
class UserPromptSubmitHookOutput:
    hook_event_name: Literal["UserPromptSubmit"] = "UserPromptSubmit"
    additional_context: str | None = None


@dataclass
class SubagentStartHookOutput:
    hook_event_name: Literal["SubagentStart"] = "SubagentStart"
    additional_context: str | None = None


@dataclass
class SetupHookOutput:
    hook_event_name: Literal["Setup"] = "Setup"
    additional_context: str | None = None


@dataclass
class PermissionDeniedHookOutput:
    hook_event_name: Literal["PermissionDenied"] = "PermissionDenied"
    retry: bool | None = None


@dataclass
class NotificationHookOutput:
    hook_event_name: Literal["Notification"] = "Notification"
    additional_context: str | None = None


@dataclass
class PermissionRequestAllowDecision:
    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = None
    updated_permissions: list[Any] | None = None


@dataclass
class PermissionRequestDenyDecision:
    behavior: Literal["deny"] = "deny"
    message: str | None = None
    interrupt: bool | None = None


@dataclass
class PermissionRequestHookOutput:
    hook_event_name: Literal["PermissionRequest"] = "PermissionRequest"
    decision: PermissionRequestAllowDecision | PermissionRequestDenyDecision | None = None


@dataclass
class ElicitationHookOutput:
    hook_event_name: Literal["Elicitation"] = "Elicitation"
    action: Literal["accept", "decline", "cancel"] | None = None
    content: dict[str, Any] | None = None


@dataclass
class ElicitationResultHookOutput:
    hook_event_name: Literal["ElicitationResult"] = "ElicitationResult"
    action: Literal["accept", "decline", "cancel"] | None = None
    content: dict[str, Any] | None = None


@dataclass
class CwdChangedHookOutput:
    hook_event_name: Literal["CwdChanged"] = "CwdChanged"
    watch_paths: list[str] | None = None


@dataclass
class FileChangedHookOutput:
    hook_event_name: Literal["FileChanged"] = "FileChanged"
    watch_paths: list[str] | None = None


@dataclass
class WorktreeCreateHookOutput:
    hook_event_name: Literal["WorktreeCreate"] = "WorktreeCreate"
    worktree_path: str = ""


@dataclass
class PostToolUseFailureHookOutput:
    hook_event_name: Literal["PostToolUseFailure"] = "PostToolUseFailure"
    additional_context: str | None = None


HookSpecificOutput = (
    PreToolUseHookOutput
    | PostToolUseHookOutput
    | SessionStartHookOutput
    | UserPromptSubmitHookOutput
    | SubagentStartHookOutput
    | SetupHookOutput
    | PermissionDeniedHookOutput
    | NotificationHookOutput
    | PermissionRequestHookOutput
    | ElicitationHookOutput
    | ElicitationResultHookOutput
    | CwdChangedHookOutput
    | FileChangedHookOutput
    | WorktreeCreateHookOutput
    | PostToolUseFailureHookOutput
)


@dataclass
class SyncHookResponse:
    """Output from a synchronously-completing hook."""

    continue_: bool | None = None  # 'continue' is a Python keyword
    suppress_output: bool | None = None
    stop_reason: str | None = None
    decision: Literal["approve", "block"] | None = None
    reason: str | None = None
    system_message: str | None = None
    hook_specific_output: HookSpecificOutput | None = None


@dataclass
class AsyncHookResponse:
    """Output from a hook that runs asynchronously."""

    async_: bool = True  # 'async' is a Python keyword
    async_timeout: int | None = None


HookJSONOutput = SyncHookResponse | AsyncHookResponse


# ---------------------------------------------------------------------------
# HookCallback
# ---------------------------------------------------------------------------


@dataclass
class HookCallback:
    """A hook that is a callback function (not a shell command)."""

    type: Literal["callback"] = "callback"
    callback: Callable[..., Any] | None = None
    timeout: int | None = None  # seconds
    internal: bool | None = None


@dataclass
class HookCallbackMatcher:
    hooks: list[HookCallback] = field(default_factory=list)
    matcher: str | None = None
    plugin_name: str | None = None


# ---------------------------------------------------------------------------
# HookProgress — displayed in UI while a hook runs
# ---------------------------------------------------------------------------


@dataclass
class HookProgress:
    type: Literal["hook_progress"] = "hook_progress"
    hook_event: str = ""
    hook_name: str = ""
    command: str = ""
    prompt_text: str | None = None
    status_message: str | None = None


# ---------------------------------------------------------------------------
# HookResult / AggregatedHookResult
# ---------------------------------------------------------------------------


@dataclass
class HookBlockingError:
    blocking_error: str
    command: str


@dataclass
class PermissionRequestResult:
    behavior: Literal["allow", "deny"]
    updated_input: dict[str, Any] | None = None
    updated_permissions: list[Any] | None = None
    message: str | None = None
    interrupt: bool | None = None


@dataclass
class HookResult:
    outcome: Literal["success", "blocking", "non_blocking_error", "cancelled"]
    message: Any | None = None  # Message
    system_message: Any | None = None  # Message
    blocking_error: HookBlockingError | None = None
    prevent_continuation: bool | None = None
    stop_reason: str | None = None
    permission_behavior: Literal["ask", "deny", "allow", "passthrough"] | None = None
    hook_permission_decision_reason: str | None = None
    additional_context: str | None = None
    initial_user_message: str | None = None
    updated_input: dict[str, Any] | None = None
    updated_mcp_tool_output: Any | None = None
    permission_request_result: PermissionRequestResult | None = None
    retry: bool | None = None


@dataclass
class AggregatedHookResult:
    message: Any | None = None  # Message
    blocking_errors: list[HookBlockingError] | None = None
    prevent_continuation: bool | None = None
    stop_reason: str | None = None
    hook_permission_decision_reason: str | None = None
    permission_behavior: str | None = None
    additional_contexts: list[str] | None = None
    initial_user_message: str | None = None
    updated_input: dict[str, Any] | None = None
    updated_mcp_tool_output: Any | None = None
    permission_request_result: PermissionRequestResult | None = None
    retry: bool | None = None


# ---------------------------------------------------------------------------
# HookCallbackContext
# ---------------------------------------------------------------------------


@dataclass
class HookCallbackContext:
    """Context passed to callback hooks for state access."""

    get_app_state: Callable[[], Any]
    update_attribution_state: Callable[[Callable[[Any], Any]], None]
