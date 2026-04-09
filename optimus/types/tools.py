"""
Tool progress type definitions — centralized to break import cycles.
Mirrors src/types/tools.ts (reconstructed from usage; file missing from archive).

All progress data types share a `type` discriminant field.
`ToolProgressData` is their union.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from optimus.types.ids import AgentId

# ---------------------------------------------------------------------------
# BashProgress — emitted by BashTool during long-running commands
# ---------------------------------------------------------------------------


@dataclass
class BashProgress:
    type: Literal["bash_progress"] = "bash_progress"
    output: str = ""
    full_output: str = ""
    elapsed_time_seconds: float = 0.0
    total_lines: int = 0
    total_bytes: int = 0
    task_id: str | None = None
    timeout_ms: int | None = None


# ---------------------------------------------------------------------------
# PowerShellProgress — emitted by PowerShellTool (same shape as BashProgress)
# ---------------------------------------------------------------------------


@dataclass
class PowerShellProgress:
    type: Literal["powershell_progress"] = "powershell_progress"
    output: str = ""
    full_output: str = ""
    elapsed_time_seconds: float = 0.0
    total_lines: int = 0
    total_bytes: int = 0
    task_id: str | None = None
    timeout_ms: int | None = None


# ---------------------------------------------------------------------------
# ShellProgress — union of bash/powershell used by AgentTool
# ---------------------------------------------------------------------------

ShellProgress = BashProgress | PowerShellProgress

# ---------------------------------------------------------------------------
# MCPProgress — emitted by MCPTool during MCP server calls
# ---------------------------------------------------------------------------


@dataclass
class MCPProgress:
    type: Literal["mcp_progress"] = "mcp_progress"
    status: Literal["started", "completed", "failed", "progress"] = "started"
    server_name: str = ""
    tool_name: str = ""
    elapsed_time_ms: float | None = None
    progress: float | None = None
    total: float | None = None


# ---------------------------------------------------------------------------
# AgentToolProgress — emitted by AgentTool for each sub-agent message
# ---------------------------------------------------------------------------


@dataclass
class AgentToolProgress:
    type: Literal["agent_progress"] = "agent_progress"
    message: Any = None  # NormalizedUserMessage | NormalizedAssistantMessage
    prompt: str = ""
    agent_id: AgentId | None = None


# ---------------------------------------------------------------------------
# SkillToolProgress — emitted by SkillTool
# ---------------------------------------------------------------------------


@dataclass
class SkillToolProgress:
    type: Literal["skill_progress"] = "skill_progress"
    prompt: str = ""
    agent_id: AgentId | None = None


# ---------------------------------------------------------------------------
# WebSearchProgress — emitted by WebSearchTool
# ---------------------------------------------------------------------------


@dataclass
class WebSearchQueryUpdate:
    type: Literal["query_update"] = "query_update"
    query: str = ""


@dataclass
class WebSearchResultsReceived:
    type: Literal["search_results_received"] = "search_results_received"
    result_count: int = 0
    query: str = ""


WebSearchProgress = WebSearchQueryUpdate | WebSearchResultsReceived

# ---------------------------------------------------------------------------
# TaskOutputProgress — emitted by TaskOutputTool while waiting for a task
# ---------------------------------------------------------------------------


@dataclass
class TaskOutputProgress:
    type: Literal["waiting_for_task"] = "waiting_for_task"
    task_description: str = ""
    task_type: str = ""


# ---------------------------------------------------------------------------
# REPLToolProgress — emitted by REPLTool
# ---------------------------------------------------------------------------


@dataclass
class REPLToolProgress:
    type: Literal["repl_progress"] = "repl_progress"
    output: str = ""


# ---------------------------------------------------------------------------
# ToolProgressData — discriminated union of all progress types
# ---------------------------------------------------------------------------

ToolProgressData = (
    BashProgress
    | PowerShellProgress
    | MCPProgress
    | AgentToolProgress
    | SkillToolProgress
    | WebSearchQueryUpdate
    | WebSearchResultsReceived
    | TaskOutputProgress
    | REPLToolProgress
)
