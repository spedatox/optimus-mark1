"""ExitPlanModeTool — exit plan mode and begin executing the approved plan."""
from __future__ import annotations
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

EXIT_PLAN_MODE_TOOL_NAME = "ExitPlanMode"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_approved": {
            "type": "boolean",
            "description": "Whether the user approved the plan.",
        },
    },
    "required": [],
}

DESCRIPTION = """\
Exit plan mode to begin executing the approved plan.
Call this after the user has reviewed and approved your plan.
Once called, file edits and shell commands will execute normally.
"""


class ExitPlanModeTool(Tool):
    name: str = EXIT_PLAN_MODE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        try:
            from optimus.bootstrap.state import set_permission_mode
            set_permission_mode("default")
        except (ImportError, AttributeError):
            pass
        return [{"type": "text", "text": "Exited plan mode. Proceeding with execution."}]


exit_plan_mode_tool = ExitPlanModeTool()
