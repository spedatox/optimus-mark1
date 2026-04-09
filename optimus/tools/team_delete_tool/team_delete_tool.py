"""TeamDeleteTool — disband a swarm team and clean up its resources."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TEAM_DELETE_TOOL_NAME = "TeamDelete"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}

DESCRIPTION = "Disband the current swarm team and clean up all associated resources."


class TeamDeleteTool(Tool):
    name: str = TEAM_DELETE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.swarm.team_helpers import (
            cleanup_team_directories, get_current_team_name
        )

        team_name = get_current_team_name()
        if not team_name:
            return [{"type": "text", "text": json.dumps({
                "success": False,
                "message": "No active team found.",
            })}]

        try:
            await cleanup_team_directories(team_name)
        except Exception as exc:
            return [{"type": "text", "text": json.dumps({
                "success": False,
                "message": f"Error cleaning up team '{team_name}': {exc}",
            })}]

        result = {
            "success": True,
            "message": f"Team '{team_name}' disbanded and resources cleaned up.",
            "team_name": team_name,
        }
        return [{"type": "text", "text": json.dumps(result)}]


team_delete_tool = TeamDeleteTool()
