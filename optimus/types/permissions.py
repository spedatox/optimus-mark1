"""
Pure permission type definitions.
Mirrors src/types/permissions.ts

Extracted to break import cycles. Contains only type definitions and constants
with no runtime dependencies beyond stdlib.
"""
from __future__ import annotations

from typing import Any, Literal

# ---------------------------------------------------------------------------
# Permission Modes
# ---------------------------------------------------------------------------

EXTERNAL_PERMISSION_MODES = ("acceptEdits", "bypassPermissions", "default", "dontAsk", "plan")

ExternalPermissionMode = Literal["acceptEdits", "bypassPermissions", "default", "dontAsk", "plan"]

# Internal modes extend external with 'auto' and 'bubble'
InternalPermissionMode = Literal[
    "acceptEdits", "bypassPermissions", "default", "dontAsk", "plan", "auto", "bubble"
]

PermissionMode = InternalPermissionMode

# Runtime-addressable modes (excludes 'bubble' which is internal state only)
INTERNAL_PERMISSION_MODES: tuple[str, ...] = EXTERNAL_PERMISSION_MODES + ("auto",)
PERMISSION_MODES = INTERNAL_PERMISSION_MODES

# ---------------------------------------------------------------------------
# Permission Behaviors
# ---------------------------------------------------------------------------

PermissionBehavior = Literal["allow", "deny", "ask"]

# ---------------------------------------------------------------------------
# Permission Rules
# ---------------------------------------------------------------------------

PermissionRuleSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
]


class PermissionRuleValue:
    """The value of a permission rule — specifies which tool and optional content."""

    __slots__ = ("tool_name", "rule_content")

    def __init__(self, tool_name: str, rule_content: str | None = None) -> None:
        self.tool_name = tool_name
        self.rule_content = rule_content

    def __repr__(self) -> str:
        return f"PermissionRuleValue(tool_name={self.tool_name!r}, rule_content={self.rule_content!r})"


class PermissionRule:
    """A permission rule with its source and behavior."""

    __slots__ = ("source", "rule_behavior", "rule_value")

    def __init__(
        self,
        source: PermissionRuleSource,
        rule_behavior: PermissionBehavior,
        rule_value: PermissionRuleValue,
    ) -> None:
        self.source = source
        self.rule_behavior = rule_behavior
        self.rule_value = rule_value


# ---------------------------------------------------------------------------
# Permission Updates
# ---------------------------------------------------------------------------

PermissionUpdateDestination = Literal[
    "userSettings", "projectSettings", "localSettings", "session", "cliArg"
]

WorkingDirectorySource = PermissionRuleSource


class AdditionalWorkingDirectory:
    """An additional directory included in permission scope."""

    __slots__ = ("path", "source")

    def __init__(self, path: str, source: WorkingDirectorySource) -> None:
        self.path = path
        self.source = source


# ---------------------------------------------------------------------------
# Permission Decisions & Results
# ---------------------------------------------------------------------------


class PermissionCommandMetadata:
    """Minimal command shape for permission metadata."""

    def __init__(self, name: str, description: str | None = None, **kwargs: Any) -> None:
        self.name = name
        self.description = description
        self._extra = kwargs


PermissionMetadata = dict[Literal["command"], PermissionCommandMetadata] | None


class ClassifierUsage:
    __slots__ = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )

    def __init__(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens


class PendingClassifierCheck:
    """Metadata for a pending classifier check that will run asynchronously."""

    __slots__ = ("command", "cwd", "descriptions")

    def __init__(self, command: str, cwd: str, descriptions: list[str]) -> None:
        self.command = command
        self.cwd = cwd
        self.descriptions = descriptions


# PermissionDecisionReason variants — represented as tagged dicts for simplicity.
# In full Pydantic, each would be a BaseModel with a Literal type field.
PermissionDecisionReason = dict[str, Any]


class PermissionAllowDecision:
    behavior: Literal["allow"] = "allow"

    def __init__(
        self,
        updated_input: dict[str, Any] | None = None,
        user_modified: bool | None = None,
        decision_reason: PermissionDecisionReason | None = None,
        tool_use_id: str | None = None,
        accept_feedback: str | None = None,
        content_blocks: list[Any] | None = None,
    ) -> None:
        self.updated_input = updated_input
        self.user_modified = user_modified
        self.decision_reason = decision_reason
        self.tool_use_id = tool_use_id
        self.accept_feedback = accept_feedback
        self.content_blocks = content_blocks


class PermissionAskDecision:
    behavior: Literal["ask"] = "ask"

    def __init__(
        self,
        message: str,
        updated_input: dict[str, Any] | None = None,
        decision_reason: PermissionDecisionReason | None = None,
        suggestions: list[Any] | None = None,
        blocked_path: str | None = None,
        metadata: PermissionMetadata = None,
        is_bash_security_check_for_misparsing: bool | None = None,
        pending_classifier_check: PendingClassifierCheck | None = None,
        content_blocks: list[Any] | None = None,
    ) -> None:
        self.message = message
        self.updated_input = updated_input
        self.decision_reason = decision_reason
        self.suggestions = suggestions
        self.blocked_path = blocked_path
        self.metadata = metadata
        self.is_bash_security_check_for_misparsing = is_bash_security_check_for_misparsing
        self.pending_classifier_check = pending_classifier_check
        self.content_blocks = content_blocks


class PermissionDenyDecision:
    behavior: Literal["deny"] = "deny"

    def __init__(
        self,
        message: str,
        decision_reason: PermissionDecisionReason,
        tool_use_id: str | None = None,
    ) -> None:
        self.message = message
        self.decision_reason = decision_reason
        self.tool_use_id = tool_use_id


class PermissionPassthroughDecision:
    behavior: Literal["passthrough"] = "passthrough"

    def __init__(
        self,
        message: str,
        decision_reason: PermissionDecisionReason | None = None,
        suggestions: list[Any] | None = None,
        blocked_path: str | None = None,
        pending_classifier_check: PendingClassifierCheck | None = None,
    ) -> None:
        self.message = message
        self.decision_reason = decision_reason
        self.suggestions = suggestions
        self.blocked_path = blocked_path
        self.pending_classifier_check = pending_classifier_check


PermissionDecision = PermissionAllowDecision | PermissionAskDecision | PermissionDenyDecision
PermissionResult = (
    PermissionAllowDecision
    | PermissionAskDecision
    | PermissionDenyDecision
    | PermissionPassthroughDecision
)

# ---------------------------------------------------------------------------
# Classifier Types
# ---------------------------------------------------------------------------

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

ClassifierBehavior = Literal["deny", "ask", "allow"]


class ClassifierResult:
    __slots__ = ("matches", "matched_description", "confidence", "reason")

    def __init__(
        self,
        matches: bool,
        confidence: Literal["high", "medium", "low"],
        reason: str,
        matched_description: str | None = None,
    ) -> None:
        self.matches = matches
        self.matched_description = matched_description
        self.confidence = confidence
        self.reason = reason


class YoloClassifierResult:
    def __init__(
        self,
        should_block: bool,
        reason: str,
        model: str,
        thinking: str | None = None,
        unavailable: bool | None = None,
        transcript_too_long: bool | None = None,
        usage: ClassifierUsage | None = None,
        duration_ms: float | None = None,
        prompt_lengths: dict[str, int] | None = None,
        error_dump_path: str | None = None,
        stage: Literal["fast", "thinking"] | None = None,
        stage1_usage: ClassifierUsage | None = None,
        stage1_duration_ms: float | None = None,
        stage1_request_id: str | None = None,
        stage1_msg_id: str | None = None,
        stage2_usage: ClassifierUsage | None = None,
        stage2_duration_ms: float | None = None,
        stage2_request_id: str | None = None,
        stage2_msg_id: str | None = None,
    ) -> None:
        self.should_block = should_block
        self.reason = reason
        self.model = model
        self.thinking = thinking
        self.unavailable = unavailable
        self.transcript_too_long = transcript_too_long
        self.usage = usage
        self.duration_ms = duration_ms
        self.prompt_lengths = prompt_lengths
        self.error_dump_path = error_dump_path
        self.stage = stage
        self.stage1_usage = stage1_usage
        self.stage1_duration_ms = stage1_duration_ms
        self.stage1_request_id = stage1_request_id
        self.stage1_msg_id = stage1_msg_id
        self.stage2_usage = stage2_usage
        self.stage2_duration_ms = stage2_duration_ms
        self.stage2_request_id = stage2_request_id
        self.stage2_msg_id = stage2_msg_id


class PermissionExplanation:
    __slots__ = ("risk_level", "explanation", "reasoning", "risk")

    def __init__(
        self,
        risk_level: RiskLevel,
        explanation: str,
        reasoning: str,
        risk: str,
    ) -> None:
        self.risk_level = risk_level
        self.explanation = explanation
        self.reasoning = reasoning
        self.risk = risk


# ---------------------------------------------------------------------------
# Tool Permission Context
# ---------------------------------------------------------------------------

ToolPermissionRulesBySource = dict[str, list[str]]


class ToolPermissionContext:
    """Context needed for permission checking in tools.

    Mirrors ToolPermissionContext in src/types/permissions.ts.
    """

    def __init__(
        self,
        mode: PermissionMode = "default",
        additional_working_directories: dict[str, AdditionalWorkingDirectory] | None = None,
        always_allow_rules: ToolPermissionRulesBySource | None = None,
        always_deny_rules: ToolPermissionRulesBySource | None = None,
        always_ask_rules: ToolPermissionRulesBySource | None = None,
        is_bypass_permissions_mode_available: bool = False,
        is_auto_mode_available: bool | None = None,
        stripped_dangerous_rules: ToolPermissionRulesBySource | None = None,
        should_avoid_permission_prompts: bool | None = None,
        await_automated_checks_before_dialog: bool | None = None,
        pre_plan_mode: PermissionMode | None = None,
    ) -> None:
        self.mode = mode
        self.additional_working_directories: dict[str, AdditionalWorkingDirectory] = (
            additional_working_directories or {}
        )
        self.always_allow_rules: ToolPermissionRulesBySource = always_allow_rules or {}
        self.always_deny_rules: ToolPermissionRulesBySource = always_deny_rules or {}
        self.always_ask_rules: ToolPermissionRulesBySource = always_ask_rules or {}
        self.is_bypass_permissions_mode_available = is_bypass_permissions_mode_available
        self.is_auto_mode_available = is_auto_mode_available
        self.stripped_dangerous_rules = stripped_dangerous_rules
        self.should_avoid_permission_prompts = should_avoid_permission_prompts
        self.await_automated_checks_before_dialog = await_automated_checks_before_dialog
        self.pre_plan_mode = pre_plan_mode


def get_empty_tool_permission_context() -> ToolPermissionContext:
    """Return a minimal default ToolPermissionContext."""
    return ToolPermissionContext()
