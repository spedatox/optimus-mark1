"""EnterPlanModeTool — switch to plan mode (read-only planning)."""
from __future__ import annotations
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

ENTER_PLAN_MODE_TOOL_NAME = "EnterPlanMode"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan": {"type": "string", "description": "The plan to present to the user for approval."},
    },
    "required": ["plan"],
}

DESCRIPTION = """\
Switch to plan mode to present a plan to the user before making changes.
In plan mode, no file edits or shell commands are executed without user approval.
Use this before making significant changes to give the user a chance to review.
"""


class EnterPlanModeTool(Tool):
    name: str = ENTER_PLAN_MODE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        plan: str = input_data.get("plan", "")
        # Signal the runtime to switch to plan mode
        try:
            from optimus.bootstrap.state import set_permission_mode
            set_permission_mode("plan")
        except (ImportError, AttributeError):
            pass
        return [{"type": "text", "text": f"[PLAN MODE]\n{plan}"}]


enter_plan_mode_tool = EnterPlanModeTool()
