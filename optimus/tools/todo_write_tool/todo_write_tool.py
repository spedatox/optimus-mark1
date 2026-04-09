"""TodoWriteTool — structured task list management. Mirrors src/tools/TodoWriteTool/TodoWriteTool.ts"""
from __future__ import annotations
from typing import Any, Literal
from optimus.tool import Tool, ToolUseContext, ValidationResult

TODO_WRITE_TOOL_NAME = "TodoWrite"

# In-memory todo list (per session)
_todos: list[dict[str, Any]] = []

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "content": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["id", "content", "status", "priority"],
            },
            "description": "The updated todo list.",
        },
    },
    "required": ["todos"],
}

DESCRIPTION = """\
Create and manage a structured task list for tracking progress on complex tasks.
Use this to plan multi-step work, track what's been done, and communicate progress.
Mark tasks as pending, in_progress, or completed.
Only one task should be in_progress at a time.
"""


class TodoWriteTool(Tool):
    name: str = TODO_WRITE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        global _todos
        _todos = input_data.get("todos", [])
        count = len(_todos)
        done = sum(1 for t in _todos if t.get("status") == "completed")
        return [{"type": "text", "text": f"Todos updated: {done}/{count} completed."}]


def get_todos() -> list[dict[str, Any]]:
    return list(_todos)


todo_write_tool = TodoWriteTool()
