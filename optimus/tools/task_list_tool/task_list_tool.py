"""TaskListTool — list all tasks in the current task list."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_LIST_TOOL_NAME = "TaskList"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}

DESCRIPTION = "List all tasks in the current task list."


class TaskListTool(Tool):
    name: str = TASK_LIST_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.tasks import list_tasks

        tasks = list_tasks()
        result = {"tasks": tasks}
        return [{"type": "text", "text": json.dumps(result)}]


task_list_tool = TaskListTool()
