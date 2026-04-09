"""
The Tool Protocol — the foundation of the entire tool system.
Mirrors src/Tool.ts

Every tool in the system conforms to this Protocol. This is the single most
important file in the codebase. All 40+ tools implement these methods.

TypeScript uses a structural type (interface Tool<Input, Output, P>) plus a
`buildTool()` factory that fills in defaults. Python equivalent:
  - `Tool` is a typed Protocol for structural subtype checking
  - `build_tool()` is a factory that returns a ToolImpl dataclass with defaults merged
  - Each concrete tool is a module-level singleton produced by build_tool()
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal, Protocol, TypeVar, runtime_checkable

from optimus.types.ids import AgentId
from optimus.types.message import AssistantMessage, Message, SystemMessage
from optimus.types.permissions import PermissionResult, ToolPermissionContext
from optimus.types.tools import ToolProgressData

if TYPE_CHECKING:
    pass  # forward-declare complex types to break cycles

# ---------------------------------------------------------------------------
# Schema types
# ---------------------------------------------------------------------------

ToolInputJSONSchema = dict[str, Any]  # Must have type="object"

# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResultOk:
    result: Literal[True] = True


@dataclass
class ValidationResultErr:
    result: Literal[False] = False
    message: str = ""
    error_code: int = 0


ValidationResult = ValidationResultOk | ValidationResultErr


# ---------------------------------------------------------------------------
# Progress types
# ---------------------------------------------------------------------------

P = TypeVar("P", bound=ToolProgressData)


@dataclass
class ToolProgress:
    """Wraps progress data with the tool_use_id that generated it."""

    tool_use_id: str
    data: ToolProgressData


ToolCallProgress = Callable[[ToolProgress], None]


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Return value from Tool.call()."""

    data: Any
    new_messages: list[Any] | None = None       # Message variants
    context_modifier: Callable[[Any], Any] | None = None  # (ToolUseContext) -> ToolUseContext
    mcp_meta: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# ToolUseContext
# ---------------------------------------------------------------------------


@dataclass
class ToolUseOptions:
    commands: list[Any] = field(default_factory=list)
    debug: bool = False
    main_loop_model: str = ""
    tools: list[Any] = field(default_factory=list)  # Tools
    verbose: bool = False
    thinking_config: Any = None
    mcp_clients: list[Any] = field(default_factory=list)
    mcp_resources: dict[str, list[Any]] = field(default_factory=dict)
    is_non_interactive_session: bool = False
    agent_definitions: Any = None
    max_budget_usd: float | None = None
    custom_system_prompt: str | None = None
    append_system_prompt: str | None = None
    query_source: str | None = None
    refresh_tools: Callable[[], list[Any]] | None = None


@dataclass
class QueryChainTracking:
    chain_id: str
    depth: int


class ToolUseContext:
    """
    Context passed to every tool.call() invocation.
    Mirrors ToolUseContext in src/Tool.ts — the shape that every tool receives.
    """

    def __init__(
        self,
        options: ToolUseOptions | None = None,
        abort_controller: Any | None = None,
        get_app_state: Callable[[], Any] | None = None,
        set_app_state: Callable[[Callable[[Any], Any]], None] | None = None,
        set_app_state_for_tasks: Callable[[Callable[[Any], Any]], None] | None = None,
        handle_elicitation: Any | None = None,
        set_tool_jsx: Any | None = None,
        add_notification: Callable[[Any], None] | None = None,
        append_system_message: Callable[[Any], None] | None = None,
        send_os_notification: Callable[[dict[str, str]], None] | None = None,
        nested_memory_attachment_triggers: set[str] | None = None,
        loaded_nested_memory_paths: set[str] | None = None,
        dynamic_skill_dir_triggers: set[str] | None = None,
        discovered_skill_names: set[str] | None = None,
        user_modified: bool | None = None,
        set_in_progress_tool_use_ids: Callable[[Callable[[set[str]], set[str]]], None] | None = None,
        set_has_interruptible_tool_in_progress: Callable[[bool], None] | None = None,
        set_response_length: Callable[[Callable[[int], int]], None] | None = None,
        push_api_metrics_entry: Callable[[float], None] | None = None,
        set_stream_mode: Any | None = None,
        on_compact_progress: Callable[[Any], None] | None = None,
        set_sdk_status: Any | None = None,
        open_message_selector: Callable[[], None] | None = None,
        update_file_history_state: Callable[[Callable[[Any], Any]], None] | None = None,
        update_attribution_state: Callable[[Callable[[Any], Any]], None] | None = None,
        set_conversation_id: Callable[[str], None] | None = None,
        agent_id: AgentId | None = None,
        agent_type: str | None = None,
        require_can_use_tool: bool | None = None,
        messages: list[Message] | None = None,
        file_reading_limits: dict[str, int] | None = None,
        glob_limits: dict[str, int] | None = None,
        tool_decisions: dict[str, Any] | None = None,
        query_tracking: QueryChainTracking | None = None,
        request_prompt: Any | None = None,
        tool_use_id: str | None = None,
        critical_system_reminder_experimental: str | None = None,
        preserve_tool_use_results: bool | None = None,
        local_denial_tracking: Any | None = None,
        content_replacement_state: Any | None = None,
        rendered_system_prompt: Any | None = None,
        read_file_state: Any | None = None,
    ) -> None:
        self.options = options or ToolUseOptions()
        self.abort_controller = abort_controller or asyncio.Event()
        self.get_app_state = get_app_state or (lambda: None)
        self.set_app_state = set_app_state or (lambda f: None)
        self.set_app_state_for_tasks = set_app_state_for_tasks
        self.handle_elicitation = handle_elicitation
        self.set_tool_jsx = set_tool_jsx
        self.add_notification = add_notification
        self.append_system_message = append_system_message
        self.send_os_notification = send_os_notification
        self.nested_memory_attachment_triggers = nested_memory_attachment_triggers
        self.loaded_nested_memory_paths = loaded_nested_memory_paths
        self.dynamic_skill_dir_triggers = dynamic_skill_dir_triggers
        self.discovered_skill_names = discovered_skill_names
        self.user_modified = user_modified
        self.set_in_progress_tool_use_ids = set_in_progress_tool_use_ids or (lambda f: None)
        self.set_has_interruptible_tool_in_progress = set_has_interruptible_tool_in_progress
        self.set_response_length = set_response_length or (lambda f: None)
        self.push_api_metrics_entry = push_api_metrics_entry
        self.set_stream_mode = set_stream_mode
        self.on_compact_progress = on_compact_progress
        self.set_sdk_status = set_sdk_status
        self.open_message_selector = open_message_selector
        self.update_file_history_state = update_file_history_state or (lambda f: None)
        self.update_attribution_state = update_attribution_state or (lambda f: None)
        self.set_conversation_id = set_conversation_id
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.require_can_use_tool = require_can_use_tool
        self.messages: list[Message] = messages or []
        self.file_reading_limits = file_reading_limits
        self.glob_limits = glob_limits
        self.tool_decisions = tool_decisions
        self.query_tracking = query_tracking
        self.request_prompt = request_prompt
        self.tool_use_id = tool_use_id
        self.critical_system_reminder_experimental = critical_system_reminder_experimental
        self.preserve_tool_use_results = preserve_tool_use_results
        self.local_denial_tracking = local_denial_tracking
        self.content_replacement_state = content_replacement_state
        self.rendered_system_prompt = rendered_system_prompt
        self.read_file_state = read_file_state


# ---------------------------------------------------------------------------
# ToolPermissionContext re-export (convenience)
# ---------------------------------------------------------------------------
# Imported at top from types/permissions.py


# ---------------------------------------------------------------------------
# CompactProgressEvent
# ---------------------------------------------------------------------------

CompactProgressEvent = dict[str, Any]  # typed dict variant, simplified


# ---------------------------------------------------------------------------
# Tool Protocol
# ---------------------------------------------------------------------------

# Python's Protocol enables structural typing — any object with the right
# methods/attributes satisfies Tool without explicit inheritance.


@runtime_checkable
class Tool(Protocol):
    """
    The Tool protocol — every tool in the system must satisfy this interface.

    Mirrors the `Tool<Input, Output, P>` TypeScript interface in src/Tool.ts.
    """

    name: str
    max_result_size_chars: int

    # Optional fields with defaults provided by build_tool()
    aliases: list[str]
    search_hint: str | None
    is_mcp: bool | None
    is_lsp: bool | None
    should_defer: bool | None
    always_load: bool | None
    strict: bool | None
    mcp_info: dict[str, str] | None  # {server_name, tool_name}

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        can_use_tool: Any,
        parent_message: AssistantMessage,
        on_progress: ToolCallProgress | None = None,
    ) -> ToolResult: ...

    async def description(
        self,
        input_: dict[str, Any],
        options: dict[str, Any],
    ) -> str: ...

    async def prompt(
        self,
        options: dict[str, Any],
    ) -> str: ...

    async def check_permissions(
        self,
        input_: dict[str, Any],
        context: ToolUseContext,
    ) -> PermissionResult: ...

    def is_enabled(self) -> bool: ...

    def is_concurrency_safe(self, input_: dict[str, Any]) -> bool: ...

    def is_read_only(self, input_: dict[str, Any]) -> bool: ...

    def is_destructive(self, input_: dict[str, Any]) -> bool: ...

    def user_facing_name(self, input_: dict[str, Any] | None) -> str: ...

    def to_auto_classifier_input(self, input_: dict[str, Any]) -> Any: ...

    def map_tool_result_to_tool_result_block_param(
        self,
        content: Any,
        tool_use_id: str,
    ) -> dict[str, Any]: ...

    def render_tool_use_message(
        self,
        input_: dict[str, Any],
        options: dict[str, Any],
    ) -> Any: ...

    # Optional Protocol methods (may raise NotImplementedError)
    def inputs_equivalent(
        self, a: dict[str, Any], b: dict[str, Any]
    ) -> bool: ...

    def interrupt_behavior(self) -> Literal["cancel", "block"]: ...

    def is_search_or_read_command(
        self, input_: dict[str, Any]
    ) -> dict[str, bool]: ...

    def is_open_world(self, input_: dict[str, Any]) -> bool: ...

    def requires_user_interaction(self) -> bool: ...

    def get_path(self, input_: dict[str, Any]) -> str: ...

    async def validate_input(
        self,
        input_: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult: ...

    async def prepare_permission_matcher(
        self,
        input_: dict[str, Any],
    ) -> Callable[[str], bool]: ...

    def backfill_observable_input(self, input_: dict[str, Any]) -> None: ...

    def get_tool_use_summary(self, input_: dict[str, Any] | None) -> str | None: ...

    def get_activity_description(self, input_: dict[str, Any] | None) -> str | None: ...

    def is_transparent_wrapper(self) -> bool: ...

    def is_result_truncated(self, output: Any) -> bool: ...

    def extract_search_text(self, out: Any) -> str: ...

    def render_tool_result_message(self, content: Any, progress_messages: list[Any], options: dict[str, Any]) -> Any: ...

    def render_tool_use_progress_message(self, progress_messages: list[Any], options: dict[str, Any]) -> Any: ...

    def render_tool_use_queued_message(self) -> Any: ...

    def render_tool_use_rejected_message(self, input_: dict[str, Any], options: dict[str, Any]) -> Any: ...

    def render_tool_use_error_message(self, result: Any, options: dict[str, Any]) -> Any: ...

    def render_grouped_tool_use(self, tool_uses: list[Any], options: dict[str, Any]) -> Any: ...

    def render_tool_use_tag(self, input_: dict[str, Any] | None) -> Any: ...

    def user_facing_name_background_color(self, input_: dict[str, Any] | None) -> str | None: ...


# Alias for a list of tools
Tools = list[Tool]


# ---------------------------------------------------------------------------
# Default implementations — applied by build_tool()
# ---------------------------------------------------------------------------

# Fail-closed defaults: conservative, same semantics as TypeScript TOOL_DEFAULTS
_TOOL_DEFAULTS: dict[str, Any] = {
    "is_enabled": lambda: True,
    "is_concurrency_safe": lambda input_=None: False,
    "is_read_only": lambda input_=None: False,
    "is_destructive": lambda input_=None: False,
    "check_permissions": lambda input_, ctx=None: _default_check_permissions(input_),
    "to_auto_classifier_input": lambda input_=None: "",
    "user_facing_name": lambda input_=None: "",
    "aliases": [],
    "search_hint": None,
    "is_mcp": None,
    "is_lsp": None,
    "should_defer": None,
    "always_load": None,
    "strict": None,
    "mcp_info": None,
}


async def _default_check_permissions(
    input_: dict[str, Any],
) -> PermissionResult:
    from optimus.types.permissions import PermissionAllowDecision

    return PermissionAllowDecision(updated_input=input_)


# ---------------------------------------------------------------------------
# build_tool() — factory that merges defaults into a tool definition
# ---------------------------------------------------------------------------


class ToolImpl:
    """
    Concrete tool object produced by build_tool().
    Holds all Tool Protocol fields; forwards missing optional methods to stubs.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name = name
        # Apply defaults then override with provided values
        for k, v in _TOOL_DEFAULTS.items():
            setattr(self, k, v)
        # Override defaults with explicit values from the definition
        for k, v in kwargs.items():
            setattr(self, k, v)
        # user_facing_name defaults to tool name if not provided
        if not kwargs.get("user_facing_name"):
            self.user_facing_name = lambda input_=None: self.name

    def __repr__(self) -> str:
        return f"<Tool name={self.name!r}>"


def build_tool(**kwargs: Any) -> ToolImpl:
    """
    Build a complete Tool from a partial definition, filling in safe defaults.

    Mirrors buildTool() in src/Tool.ts.

    All tool modules call this to create their singleton tool object:
        MyTool = build_tool(
            name="MyTool",
            max_result_size_chars=200_000,
            call=my_call_fn,
            ...
        )
    """
    name = kwargs.pop("name")
    return ToolImpl(name=name, **kwargs)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def tool_matches_name(tool: Any, name: str) -> bool:
    """Check if a tool matches the given name (primary name or alias)."""
    return tool.name == name or (
        hasattr(tool, "aliases") and name in (tool.aliases or [])
    )


def find_tool_by_name(tools: list[Any], name: str) -> Any | None:
    """Find a tool by name or alias from a list of tools."""
    for t in tools:
        if tool_matches_name(t, name):
            return t
    return None


def filter_tool_progress_messages(
    progress_messages: list[Any],
) -> list[Any]:
    """Filter out hook_progress messages, returning only tool progress messages."""
    return [m for m in progress_messages if getattr(m.data, "type", None) != "hook_progress"]
