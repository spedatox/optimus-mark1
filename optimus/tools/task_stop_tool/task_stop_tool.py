"""TaskStopTool — stop a running background task."""
from __future__ import annotations
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_STOP_TOOL_NAME = "TaskStop"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "The ID of the background task to stop.",
        },
        "shell_id": {
            "type": "string",
            "description": "Deprecated: use task_id instead.",
        },
    },
    "required": [],
}

DESCRIPTION = "Stop a running background task by its task_id."


class TaskStopTool(Tool):
    name: str = TASK_STOP_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.tasks.task_registry import get_task_registry

        task_id: str | None = input_data.get("task_id") or input_data.get("shell_id")
        if not task_id:
            return [{"type": "text", "text": "Error: task_id is required."}]

        registry = get_task_registry()
        task = registry.get(task_id)
        if task is None:
            return [{"type": "text", "text": f"Task not found: {task_id}"}]

        try:
            await task.stop()
        except Exception as exc:
            return [{"type": "text", "text": f"Error stopping task {task_id}: {exc}"}]

        return [{"type": "text", "text": f"Task {task_id} stopped."}]


task_stop_tool = TaskStopTool()
