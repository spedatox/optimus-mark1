"""
Tool registry — assembles and filters the full tool pool.
Mirrors src/tools.ts

This module is the single source of truth for which tools are available
in the current environment. It respects environment variables, feature flags,
and permission context to determine the active tool set.
"""
from __future__ import annotations

import os
from typing import Any

from optimus.tool import Tool, Tools, tool_matches_name, find_tool_by_name
from optimus.types.permissions import ToolPermissionContext
from optimus.utils.features import feature
from optimus.utils.env_utils import is_env_truthy

# ---------------------------------------------------------------------------
# Tool name constants (canonical string IDs used everywhere)
# ---------------------------------------------------------------------------

AGENT_TOOL_NAME = "Agent"
TASK_OUTPUT_TOOL_NAME = "Task"
BASH_TOOL_NAME = "Bash"
GLOB_TOOL_NAME = "Glob"
GREP_TOOL_NAME = "Grep"
EXIT_PLAN_MODE_V2_TOOL_NAME = "ExitPlanMode"
FILE_READ_TOOL_NAME = "Read"
FILE_EDIT_TOOL_NAME = "Edit"
FILE_WRITE_TOOL_NAME = "Write"
NOTEBOOK_EDIT_TOOL_NAME = "NotebookEdit"
WEB_FETCH_TOOL_NAME = "WebFetch"
TODO_WRITE_TOOL_NAME = "TodoWrite"
WEB_SEARCH_TOOL_NAME = "WebSearch"
TASK_STOP_TOOL_NAME = "TaskStop"
ASK_USER_QUESTION_TOOL_NAME = "AskFollowupQuestion"
SKILL_TOOL_NAME = "Skill"
ENTER_PLAN_MODE_TOOL_NAME = "EnterPlanMode"
CONFIG_TOOL_NAME = "Config"
TASK_CREATE_TOOL_NAME = "TaskCreate"
TASK_GET_TOOL_NAME = "TaskGet"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"
TASK_LIST_TOOL_NAME = "TaskList"
LSP_TOOL_NAME = "LSP"
ENTER_WORKTREE_TOOL_NAME = "EnterWorktree"
EXIT_WORKTREE_TOOL_NAME = "ExitWorktree"
SEND_MESSAGE_TOOL_NAME = "SendMessage"
TEAM_CREATE_TOOL_NAME = "TeamCreate"
TEAM_DELETE_TOOL_NAME = "TeamDelete"
REPL_TOOL_NAME = "REPL"
SLEEP_TOOL_NAME = "Sleep"
CRON_CREATE_TOOL_NAME = "CronCreate"
CRON_DELETE_TOOL_NAME = "CronDelete"
CRON_LIST_TOOL_NAME = "CronList"
REMOTE_TRIGGER_TOOL_NAME = "RemoteTrigger"
BRIEF_TOOL_NAME = "Brief"
POWERSHELL_TOOL_NAME = "PowerShell"
LIST_MCP_RESOURCES_TOOL_NAME = "mcp__list_resources"
READ_MCP_RESOURCE_TOOL_NAME = "mcp__read_resource"
TOOL_SEARCH_TOOL_NAME = "ToolSearch"
SYNTHETIC_OUTPUT_TOOL_NAME = "SyntheticOutput"
NOTEBOOK_EDIT_TOOL_NAME = "NotebookEdit"

# REPL-only tools — hidden from model when REPL is enabled (model uses REPL directly)
REPL_ONLY_TOOLS: frozenset[str] = frozenset([
    BASH_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    FILE_READ_TOOL_NAME,
    FILE_EDIT_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
    NOTEBOOK_EDIT_TOOL_NAME,
])

# ---------------------------------------------------------------------------
# Tool preset
# ---------------------------------------------------------------------------

TOOL_PRESETS = ("default",)
ToolPreset = str


def parse_tool_preset(preset: str) -> ToolPreset | None:
    lower = preset.lower()
    return lower if lower in TOOL_PRESETS else None


# ---------------------------------------------------------------------------
# Lazy tool importers (break circular imports)
# ---------------------------------------------------------------------------

def _get_team_create_tool() -> Any:
    from optimus.tools.team_create_tool import TeamCreateTool
    return TeamCreateTool


def _get_team_delete_tool() -> Any:
    from optimus.tools.team_delete_tool import TeamDeleteTool
    return TeamDeleteTool


def _get_send_message_tool() -> Any:
    from optimus.tools.send_message_tool import SendMessageTool
    return SendMessageTool


def _get_powershell_tool() -> Any:
    from optimus.utils.shell.shell_tool_utils import is_powershell_tool_enabled
    if not is_powershell_tool_enabled():
        return None
    from optimus.tools.powershell_tool import PowerShellTool
    return PowerShellTool


def _get_repl_tool() -> Any:
    if os.environ.get("USER_TYPE") != "ant":
        return None
    try:
        from optimus.tools.repl_tool import REPLTool
        return REPLTool
    except ImportError:
        return None


def _is_repl_mode_enabled() -> bool:
    try:
        from optimus.tools.repl_tool.constants import is_repl_mode_enabled
        return is_repl_mode_enabled()
    except ImportError:
        return False


def _is_tool_search_enabled_optimistic() -> bool:
    try:
        from optimus.utils.tool_search import is_tool_search_enabled_optimistic
        return is_tool_search_enabled_optimistic()
    except ImportError:
        return False


def _is_todo_v2_enabled() -> bool:
    try:
        from optimus.utils.tasks import is_todo_v2_enabled
        return is_todo_v2_enabled()
    except ImportError:
        return False


def _is_agent_swarms_enabled() -> bool:
    try:
        from optimus.utils.agent_swarms_enabled import is_agent_swarms_enabled
        return is_agent_swarms_enabled()
    except ImportError:
        return False


def _is_worktree_mode_enabled() -> bool:
    try:
        from optimus.utils.worktree_mode_enabled import is_worktree_mode_enabled
        return is_worktree_mode_enabled()
    except ImportError:
        return False


def _has_embedded_search_tools() -> bool:
    try:
        from optimus.utils.embedded_tools import has_embedded_search_tools
        return has_embedded_search_tools()
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Core tool imports (always present)
# ---------------------------------------------------------------------------

def _import_tool(module_path: str, class_name: str) -> Any:
    """Safely import a tool class, returning None if not found."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except (ImportError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# getAllBaseTools() equivalent
# ---------------------------------------------------------------------------

def get_all_base_tools() -> Tools:
    """
    Get the complete exhaustive list of all tools that could be available.
    This is the source of truth for ALL tools.
    Mirrors getAllBaseTools() in src/tools.ts
    """
    tools: list[Any] = []

    # Always-present core tools
    _CORE_TOOLS = [
        ("optimus.tools.agent_tool", "AgentTool"),
        ("optimus.tools.task_output_tool", "TaskOutputTool"),
        ("optimus.tools.bash_tool", "BashTool"),
        ("optimus.tools.exit_plan_mode_tool", "ExitPlanModeV2Tool"),
        ("optimus.tools.file_read_tool", "FileReadTool"),
        ("optimus.tools.file_edit_tool", "FileEditTool"),
        ("optimus.tools.file_write_tool", "FileWriteTool"),
        ("optimus.tools.notebook_edit_tool", "NotebookEditTool"),
        ("optimus.tools.web_fetch_tool", "WebFetchTool"),
        ("optimus.tools.todo_write_tool", "TodoWriteTool"),
        ("optimus.tools.web_search_tool", "WebSearchTool"),
        ("optimus.tools.task_stop_tool", "TaskStopTool"),
        ("optimus.tools.ask_user_question_tool", "AskUserQuestionTool"),
        ("optimus.tools.skill_tool", "SkillTool"),
        ("optimus.tools.enter_plan_mode_tool", "EnterPlanModeTool"),
        ("optimus.tools.brief_tool", "BriefTool"),
        ("optimus.tools.list_mcp_resources_tool", "ListMcpResourcesTool"),
        ("optimus.tools.read_mcp_resource_tool", "ReadMcpResourceTool"),
    ]

    for module_path, class_name in _CORE_TOOLS:
        tool = _import_tool(module_path, class_name)
        if tool is not None:
            tools.append(tool)

    # Glob/Grep only when embedded search tools are not available
    if not _has_embedded_search_tools():
        for module_path, class_name in [
            ("optimus.tools.glob_tool", "GlobTool"),
            ("optimus.tools.grep_tool", "GrepTool"),
        ]:
            tool = _import_tool(module_path, class_name)
            if tool is not None:
                tools.append(tool)

    # Ant-only tools
    if os.environ.get("USER_TYPE") == "ant":
        for module_path, class_name in [
            ("optimus.tools.config_tool", "ConfigTool"),
        ]:
            tool = _import_tool(module_path, class_name)
            if tool is not None:
                tools.append(tool)

    # Todo v2 task management tools
    if _is_todo_v2_enabled():
        for module_path, class_name in [
            ("optimus.tools.task_create_tool", "TaskCreateTool"),
            ("optimus.tools.task_get_tool", "TaskGetTool"),
            ("optimus.tools.task_update_tool", "TaskUpdateTool"),
            ("optimus.tools.task_list_tool", "TaskListTool"),
        ]:
            tool = _import_tool(module_path, class_name)
            if tool is not None:
                tools.append(tool)

    # LSP tool (opt-in via env var)
    if is_env_truthy(os.environ.get("ENABLE_LSP_TOOL")):
        tool = _import_tool("optimus.tools.lsp_tool", "LSPTool")
        if tool is not None:
            tools.append(tool)

    # Worktree mode
    if _is_worktree_mode_enabled():
        for module_path, class_name in [
            ("optimus.tools.enter_worktree_tool", "EnterWorktreeTool"),
            ("optimus.tools.exit_worktree_tool", "ExitWorktreeTool"),
        ]:
            tool = _import_tool(module_path, class_name)
            if tool is not None:
                tools.append(tool)

    # SendMessage (lazy to avoid circular imports)
    send_message_tool = _get_send_message_tool()
    if send_message_tool is not None:
        tools.append(send_message_tool)

    # Agent swarms (TeamCreate/Delete)
    if _is_agent_swarms_enabled():
        team_create = _get_team_create_tool()
        if team_create is not None:
            tools.append(team_create)
        team_delete = _get_team_delete_tool()
        if team_delete is not None:
            tools.append(team_delete)

    # Ant-only REPL tool
    repl_tool = _get_repl_tool()
    if repl_tool is not None:
        tools.append(repl_tool)

    # Feature-flag-gated tools
    if feature("PROACTIVE") or feature("KAIROS"):
        tool = _import_tool("optimus.tools.sleep_tool", "SleepTool")
        if tool is not None:
            tools.append(tool)

    if feature("AGENT_TRIGGERS"):
        for module_path, class_name in [
            ("optimus.tools.schedule_cron_tool.cron_create_tool", "CronCreateTool"),
            ("optimus.tools.schedule_cron_tool.cron_delete_tool", "CronDeleteTool"),
            ("optimus.tools.schedule_cron_tool.cron_list_tool", "CronListTool"),
        ]:
            tool = _import_tool(module_path, class_name)
            if tool is not None:
                tools.append(tool)

    if feature("AGENT_TRIGGERS_REMOTE"):
        tool = _import_tool("optimus.tools.remote_trigger_tool", "RemoteTriggerTool")
        if tool is not None:
            tools.append(tool)

    # PowerShell tool (platform-conditional)
    powershell_tool = _get_powershell_tool()
    if powershell_tool is not None:
        tools.append(powershell_tool)

    # ToolSearch (when tool search might be enabled)
    if _is_tool_search_enabled_optimistic():
        tool = _import_tool("optimus.tools.tool_search_tool", "ToolSearchTool")
        if tool is not None:
            tools.append(tool)

    # Test-only permission tool
    if os.environ.get("NODE_ENV") == "test":
        tool = _import_tool("optimus.tools.testing.testing_permission_tool", "TestingPermissionTool")
        if tool is not None:
            tools.append(tool)

    return tools


# ---------------------------------------------------------------------------
# get_tools_for_default_preset()
# ---------------------------------------------------------------------------

def get_tools_for_default_preset() -> list[str]:
    """Return tool names for the default preset (enabled tools only)."""
    tools = get_all_base_tools()
    return [
        t.name for t in tools
        if callable(getattr(t, "is_enabled", None)) and t.is_enabled()
    ]


# ---------------------------------------------------------------------------
# filter_tools_by_deny_rules()
# ---------------------------------------------------------------------------

def filter_tools_by_deny_rules(
    tools: list[Any],
    permission_context: ToolPermissionContext,
) -> list[Any]:
    """
    Filter out tools that are blanket-denied by the permission context.
    Mirrors filterToolsByDenyRules() in src/tools.ts
    """
    try:
        from optimus.utils.permissions.permissions import get_deny_rule_for_tool
        return [t for t in tools if not get_deny_rule_for_tool(permission_context, t)]
    except ImportError:
        return tools


# ---------------------------------------------------------------------------
# get_tools()
# ---------------------------------------------------------------------------

def get_tools(permission_context: ToolPermissionContext) -> Tools:
    """
    Get the filtered tool list for the current session.
    Respects CLAUDE_CODE_SIMPLE, REPL mode, feature flags, deny rules.
    Mirrors getTools() in src/tools.ts
    """
    from optimus.constants.tools import (
        ALL_AGENT_DISALLOWED_TOOLS,
        COORDINATOR_MODE_ALLOWED_TOOLS,
    )

    # Simple mode
    if is_env_truthy(os.environ.get("CLAUDE_CODE_SIMPLE")):
        repl_tool = _get_repl_tool()
        if _is_repl_mode_enabled() and repl_tool:
            simple: list[Any] = [repl_tool]
            # Coordinator mode additions
            if feature("COORDINATOR_MODE"):
                send_msg = _get_send_message_tool()
                task_stop = _import_tool("optimus.tools.task_stop_tool", "TaskStopTool")
                if send_msg:
                    simple.append(send_msg)
                if task_stop:
                    simple.append(task_stop)
            return filter_tools_by_deny_rules(simple, permission_context)

        simple_tools = []
        for mod, cls in [
            ("optimus.tools.bash_tool", "BashTool"),
            ("optimus.tools.file_read_tool", "FileReadTool"),
            ("optimus.tools.file_edit_tool", "FileEditTool"),
        ]:
            t = _import_tool(mod, cls)
            if t:
                simple_tools.append(t)
        if feature("COORDINATOR_MODE"):
            for mod, cls in [
                ("optimus.tools.agent_tool", "AgentTool"),
                ("optimus.tools.task_stop_tool", "TaskStopTool"),
            ]:
                t = _import_tool(mod, cls)
                if t:
                    simple_tools.append(t)
            send_msg = _get_send_message_tool()
            if send_msg:
                simple_tools.append(send_msg)
        return filter_tools_by_deny_rules(simple_tools, permission_context)

    # Special tools excluded from default get_tools() (added conditionally elsewhere)
    special_tools = {
        LIST_MCP_RESOURCES_TOOL_NAME,
        READ_MCP_RESOURCE_TOOL_NAME,
        SYNTHETIC_OUTPUT_TOOL_NAME,
    }

    tools = [t for t in get_all_base_tools() if t.name not in special_tools]
    allowed_tools = filter_tools_by_deny_rules(tools, permission_context)

    # REPL mode: hide primitive tools that REPL wraps internally
    if _is_repl_mode_enabled():
        has_repl = any(tool_matches_name(t, REPL_TOOL_NAME) for t in allowed_tools)
        if has_repl:
            allowed_tools = [t for t in allowed_tools if t.name not in REPL_ONLY_TOOLS]

    return [t for t in allowed_tools if t.is_enabled()]


# ---------------------------------------------------------------------------
# assemble_tool_pool()
# ---------------------------------------------------------------------------

def assemble_tool_pool(
    permission_context: ToolPermissionContext,
    mcp_tools: Tools,
) -> Tools:
    """
    Assemble the full tool pool combining built-in + MCP tools.
    Deduplicates by name (built-in tools take precedence).
    Maintains stable sort order within each partition for prompt cache stability.
    Mirrors assembleToolPool() in src/tools.ts
    """
    built_in_tools = get_tools(permission_context)
    allowed_mcp_tools = filter_tools_by_deny_rules(list(mcp_tools), permission_context)

    # Sort each partition by name for prompt-cache stability
    built_in_sorted = sorted(built_in_tools, key=lambda t: t.name)
    mcp_sorted = sorted(allowed_mcp_tools, key=lambda t: t.name)

    # Deduplicate: built-in tools win on name conflict
    seen: set[str] = set()
    result: list[Any] = []
    for t in built_in_sorted + mcp_sorted:
        if t.name not in seen:
            seen.add(t.name)
            result.append(t)

    return result


# ---------------------------------------------------------------------------
# get_merged_tools()
# ---------------------------------------------------------------------------

def get_merged_tools(
    permission_context: ToolPermissionContext,
    mcp_tools: Tools,
) -> Tools:
    """
    Get all tools including built-in + MCP tools (without dedup/sort).
    Use for token counting and tool-search threshold calculations.
    Mirrors getMergedTools() in src/tools.ts
    """
    built_in_tools = get_tools(permission_context)
    return list(built_in_tools) + list(mcp_tools)
