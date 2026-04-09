"""
Tools that are safe and don't need classifier checking in auto mode.
Mirrors src/utils/permissions/classifierDecision.ts
"""
from __future__ import annotations

__all__ = [
    "SAFE_YOLO_ALLOWLISTED_TOOLS",
    "is_auto_mode_allowlisted_tool",
]

# Tool names that are always safe in auto mode (read-only or coordination only).
# These skip unnecessary classifier API calls.
SAFE_YOLO_ALLOWLISTED_TOOLS: frozenset[str] = frozenset(
    [
        # Read-only file operations
        "Read",
        # Search / read-only
        "Grep",
        "Glob",
        "LSP",
        "ToolSearch",
        "ListMcpResourcesTool",
        "ReadMcpResourceTool",
        # Task management (metadata only)
        "TodoWrite",
        "TaskCreate",
        "TaskGet",
        "TaskUpdate",
        "TaskList",
        "TaskStop",
        "TaskOutput",
        # Plan mode / UI
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
        # Swarm coordination
        "TeamCreate",
        "TeamDelete",
        "SendMessage",
        # Misc safe
        "Sleep",
        # Internal classifier tool
        "yolo_classifier",
    ]
)


def is_auto_mode_allowlisted_tool(tool_name: str) -> bool:
    """Returns True if the tool is safe in auto mode and doesn't need classification."""
    return tool_name in SAFE_YOLO_ALLOWLISTED_TOOLS
