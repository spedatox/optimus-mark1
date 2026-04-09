"""TaskCreateTool — create a task in the shared task list."""
from __future__ import annotations
import json
import secrets
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_CREATE_TOOL_NAME = "TaskCreate"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "A brief title for the task.",
        },
        "description": {
            "type": "string",
            "description": "What needs to be done.",
        },
        "activeForm": {
            "type": "string",
            "description": "Present continuous form shown in spinner when in_progress.",
        },
        "metadata": {
            "type": "object",
            "description": "Arbitrary metadata to attach to the task.",
        },
    },
    "required": ["subject", "description"],
}

DESCRIPTION = "Create a task in the shared task list for tracking work."


class TaskCreateTool(Tool):
    name: str = TASK_CREATE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.tasks import create_task

        task_id = secrets.token_hex(8)
        subject: str = input_data["subject"]
        description: str = input_data["description"]
        active_form: str | None = input_data.get("activeForm")
        metadata: dict | None = input_data.get("metadata")

        task = create_task(
            task_id=task_id,
            subject=subject,
            description=description,
            active_form=active_form,
            metadata=metadata or {},
        )

        result = {"task": {"id": task["id"], "subject": task["subject"]}}
        return [{"type": "text", "text": json.dumps(result)}]


task_create_tool = TaskCreateTool()
