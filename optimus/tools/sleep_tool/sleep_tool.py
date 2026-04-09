"""SleepTool — wait for a specified duration without holding a shell process."""
from __future__ import annotations
import asyncio
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

SLEEP_TOOL_NAME = "Sleep"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "duration": {"type": "number", "description": "Duration to sleep in seconds."},
    },
    "required": ["duration"],
}

DESCRIPTION = """\
Wait for a specified duration. The user can interrupt the sleep at any time.
Prefer this over `Bash(sleep ...)` — it doesn't hold a shell process.
"""


class SleepTool(Tool):
    name: str = SLEEP_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        duration = float(input_data.get("duration", 1))
        duration = max(0.0, min(duration, 300.0))  # cap at 5 minutes
        await asyncio.sleep(duration)
        return [{"type": "text", "text": f"Slept for {duration:.1f}s."}]


sleep_tool = SleepTool()
