"""TaskGetTool — retrieve a task by ID."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_GET_TOOL_NAME = "TaskGet"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "taskId": {
            "type": "string",
            "description": "The ID of the task to retrieve.",
        },
    },
    "required": ["taskId"],
}

DESCRIPTION = "Retrieve a task by its ID from the task list."


class TaskGetTool(Tool):
    name: str = TASK_GET_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.tasks import get_task

        task_id: str = input_data["taskId"]
        task = get_task(task_id)
        result = {"task": task}
        return [{"type": "text", "text": json.dumps(result)}]


task_get_tool = TaskGetTool()
