"""
Tool-name constants and agent-tool-set definitions — port of ``src/constants/tools.ts``.

Defines the various frozen sets of tool names that govern which tools are
available in each execution context:

- :data:`ALL_AGENT_DISALLOWED_TOOLS` — tools that sub-agents may never use
  (unless running as an Anthropic-internal ``ant`` user).
- :data:`CUSTOM_AGENT_DISALLOWED_TOOLS` — superset of the above for
  custom/user-defined agents.
- :data:`ASYNC_AGENT_ALLOWED_TOOLS` — allow-list for asynchronous background
  agents (replaces a broad allow-all with an explicit safe subset).
- :data:`IN_PROCESS_TEAMMATE_ALLOWED_TOOLS` — additional tools injected only
  for in-process teammate agents.
- :data:`COORDINATOR_MODE_ALLOWED_TOOLS` — tools available when the agent is
  running as a coordinator (orchestrator-only mode).

Tool names are string literals that match the ``name`` property exported by
each tool's TypeScript module.  See the individual tool ``constants.py`` /
``prompt.py`` files for canonical definitions once they are ported.
"""
from __future__ import annotations

import os

from optimus.utils.features import feature

# ---------------------------------------------------------------------------
# Canonical tool-name literals
# These match the TypeScript constants imported in tools.ts.
# ---------------------------------------------------------------------------

TASK_OUTPUT_TOOL_NAME: str = "Task"
EXIT_PLAN_MODE_V2_TOOL_NAME: str = "ExitPlanMode"
ENTER_PLAN_MODE_TOOL_NAME: str = "EnterPlanMode"
AGENT_TOOL_NAME: str = "Agent"
ASK_USER_QUESTION_TOOL_NAME: str = "AskFollowupQuestion"
TASK_STOP_TOOL_NAME: str = "TaskStop"
FILE_READ_TOOL_NAME: str = "Read"
WEB_SEARCH_TOOL_NAME: str = "WebSearch"
TODO_WRITE_TOOL_NAME: str = "TodoWrite"
GREP_TOOL_NAME: str = "Grep"
WEB_FETCH_TOOL_NAME: str = "WebFetch"
GLOB_TOOL_NAME: str = "Glob"
BASH_TOOL_NAME: str = "Bash"
POWERSHELL_TOOL_NAME: str = "PowerShell"
FILE_EDIT_TOOL_NAME: str = "Edit"
FILE_WRITE_TOOL_NAME: str = "Write"
NOTEBOOK_EDIT_TOOL_NAME: str = "NotebookEdit"
SKILL_TOOL_NAME: str = "Skill"
SYNTHETIC_OUTPUT_TOOL_NAME: str = "SyntheticOutput"
TOOL_SEARCH_TOOL_NAME: str = "ToolSearch"
ENTER_WORKTREE_TOOL_NAME: str = "EnterWorktree"
EXIT_WORKTREE_TOOL_NAME: str = "ExitWorktree"
SEND_MESSAGE_TOOL_NAME: str = "SendMessage"
TASK_CREATE_TOOL_NAME: str = "TaskCreate"
TASK_GET_TOOL_NAME: str = "TaskGet"
TASK_LIST_TOOL_NAME: str = "TaskList"
TASK_UPDATE_TOOL_NAME: str = "TaskUpdate"
CRON_CREATE_TOOL_NAME: str = "CronCreate"
CRON_DELETE_TOOL_NAME: str = "CronDelete"
CRON_LIST_TOOL_NAME: str = "CronList"
WORKFLOW_TOOL_NAME: str = "Workflow"

# Shell tool names mirror SHELL_TOOL_NAMES from shellToolUtils.ts.
SHELL_TOOL_NAMES: frozenset[str] = frozenset({BASH_TOOL_NAME, POWERSHELL_TOOL_NAME})

# ---------------------------------------------------------------------------
# ALL_AGENT_DISALLOWED_TOOLS
#
# Tools that sub-agents may never invoke.  When USER_TYPE=ant the AgentTool is
# permitted (enabling nested agents in internal environments); for external
# users it is blocked to prevent unbounded recursion.
#
# When the WORKFLOW_SCRIPTS feature flag is enabled the WorkflowTool is also
# blocked inside sub-agents to prevent recursive workflow execution.
# ---------------------------------------------------------------------------

_base_disallowed: set[str] = {
    TASK_OUTPUT_TOOL_NAME,
    EXIT_PLAN_MODE_V2_TOOL_NAME,
    ENTER_PLAN_MODE_TOOL_NAME,
    ASK_USER_QUESTION_TOOL_NAME,
    TASK_STOP_TOOL_NAME,
}

# Allow AgentTool for agents only when running as an Anthropic-internal user.
if os.environ.get("USER_TYPE") != "ant":
    _base_disallowed.add(AGENT_TOOL_NAME)

# Block WorkflowTool inside sub-agents when the feature flag is enabled.
if feature("WORKFLOW_SCRIPTS"):
    _base_disallowed.add(WORKFLOW_TOOL_NAME)

ALL_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset(_base_disallowed)

# ---------------------------------------------------------------------------
# CUSTOM_AGENT_DISALLOWED_TOOLS
#
# Extends ALL_AGENT_DISALLOWED_TOOLS.  Currently identical; a superset is kept
# as a separate symbol so callers can express intent and future additions can
# diverge without a breaking rename.
# ---------------------------------------------------------------------------

CUSTOM_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset(ALL_AGENT_DISALLOWED_TOOLS)

# ---------------------------------------------------------------------------
# ASYNC_AGENT_ALLOWED_TOOLS
#
# Explicit allow-list for async background agents.  Only safe, non-singleton
# tools are included.  See the source comments for the rationale behind each
# omission (AgentTool, TaskOutputTool, ExitPlanModeTool, TaskStopTool, MCP,
# terminal-singleton tools).
# ---------------------------------------------------------------------------

ASYNC_AGENT_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        FILE_READ_TOOL_NAME,
        WEB_SEARCH_TOOL_NAME,
        TODO_WRITE_TOOL_NAME,
        GREP_TOOL_NAME,
        WEB_FETCH_TOOL_NAME,
        GLOB_TOOL_NAME,
        *SHELL_TOOL_NAMES,
        FILE_EDIT_TOOL_NAME,
        FILE_WRITE_TOOL_NAME,
        NOTEBOOK_EDIT_TOOL_NAME,
        SKILL_TOOL_NAME,
        SYNTHETIC_OUTPUT_TOOL_NAME,
        TOOL_SEARCH_TOOL_NAME,
        ENTER_WORKTREE_TOOL_NAME,
        EXIT_WORKTREE_TOOL_NAME,
    }
)

# ---------------------------------------------------------------------------
# IN_PROCESS_TEAMMATE_ALLOWED_TOOLS
#
# Additional tools available only for in-process teammate agents.  These are
# injected by inProcessRunner and allowed through filterToolsForAgent via the
# isInProcessTeammate() check.
#
# Cron tools are conditionally included based on the AGENT_TRIGGERS feature
# flag; when enabled, teammate-created crons are tagged with the creating
# agentId and routed to that teammate's pendingUserMessages queue.
# ---------------------------------------------------------------------------

_teammate_tools: set[str] = {
    TASK_CREATE_TOOL_NAME,
    TASK_GET_TOOL_NAME,
    TASK_LIST_TOOL_NAME,
    TASK_UPDATE_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
}

if feature("AGENT_TRIGGERS"):
    _teammate_tools.update(
        {CRON_CREATE_TOOL_NAME, CRON_DELETE_TOOL_NAME, CRON_LIST_TOOL_NAME}
    )

IN_PROCESS_TEAMMATE_ALLOWED_TOOLS: frozenset[str] = frozenset(_teammate_tools)

# ---------------------------------------------------------------------------
# COORDINATOR_MODE_ALLOWED_TOOLS
#
# Tools available when the agent is in coordinator (orchestrator-only) mode.
# The coordinator only needs to launch/stop agents and emit output.
# ---------------------------------------------------------------------------

COORDINATOR_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        AGENT_TOOL_NAME,
        TASK_STOP_TOOL_NAME,
        SEND_MESSAGE_TOOL_NAME,
        SYNTHETIC_OUTPUT_TOOL_NAME,
    }
)
