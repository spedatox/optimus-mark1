"""TaskOutputTool — get output from a running or completed background task."""
from __future__ import annotations
import asyncio
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TASK_OUTPUT_TOOL_NAME = "TaskOutput"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "The task ID to get output from.",
        },
        "block": {
            "type": "boolean",
            "description": "Whether to wait for task completion.",
            "default": True,
        },
        "timeout": {
            "type": "number",
            "description": "Max wait time in ms (0-600000).",
            "default": 30000,
        },
    },
    "required": ["task_id"],
}

DESCRIPTION = "Get output from a running or completed background task."


class TaskOutputTool(Tool):
    name: str = TASK_OUTPUT_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.tasks.task_registry import get_task_registry

        task_id: str = input_data["task_id"]
        block: bool = input_data.get("block", True)
        timeout_ms: float = float(input_data.get("timeout", 30000))
        timeout_s = min(max(timeout_ms / 1000.0, 0.0), 600.0)

        registry = get_task_registry()
        task = registry.get(task_id)
        if task is None:
            result = {
                "retrieval_status": "not_ready",
                "task": None,
            }
            return [{"type": "text", "text": json.dumps(result)}]

        if block and task.status not in ("completed", "failed", "stopped"):
            try:
                await asyncio.wait_for(task.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                result = {
                    "retrieval_status": "timeout",
                    "task": {
                        "task_id": task_id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "description": task.description,
                        "output": task.get_partial_output(),
                    },
                }
                return [{"type": "text", "text": json.dumps(result)}]

        output = await task.get_output()
        result = {
            "retrieval_status": "success",
            "task": {
                "task_id": task_id,
                "task_type": task.task_type,
                "status": task.status,
                "description": task.description,
                "output": output,
                "exitCode": getattr(task, "exit_code", None),
                "error": getattr(task, "error", None),
            },
        }
        return [{"type": "text", "text": json.dumps(result)}]


task_output_tool = TaskOutputTool()
