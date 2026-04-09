"""TaskUpdateTool — update a task's status, subject, or description."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_UPDATE_TOOL_NAME = "TaskUpdate"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "taskId": {"type": "string", "description": "The ID of the task to update."},
        "subject": {"type": "string", "description": "New subject for the task."},
        "description": {"type": "string", "description": "New description for the task."},
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "blocked", "deleted"],
            "description": "New status.",
        },
    },
    "required": ["taskId"],
}

DESCRIPTION = "Update a task's status, subject, or description."


class TaskUpdateTool(Tool):
    name: str = TASK_UPDATE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.tasks import update_task, delete_task, get_task

        task_id: str = input_data["taskId"]
        status: str | None = input_data.get("status")

        if status == "deleted":
            delete_task(task_id)
            return [{"type": "text", "text": json.dumps({"task": {"id": task_id, "status": "deleted"}})}]

        updates: dict[str, Any] = {}
        if "subject" in input_data:
            updates["subject"] = input_data["subject"]
        if "description" in input_data:
            updates["description"] = input_data["description"]
        if status:
            updates["status"] = status

        task = update_task(task_id, **updates)
        return [{"type": "text", "text": json.dumps({"task": task})}]


task_update_tool = TaskUpdateTool()
