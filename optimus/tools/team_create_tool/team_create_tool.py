"""TeamCreateTool — create a new swarm team with a lead agent."""
from __future__ import annotations
import json
import secrets
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TEAM_CREATE_TOOL_NAME = "TeamCreate"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "team_name": {
            "type": "string",
            "description": "Name for the new team to create.",
        },
        "description": {
            "type": "string",
            "description": "Team description/purpose.",
        },
        "agent_type": {
            "type": "string",
            "description": "Type/role of the team lead (e.g., 'researcher', 'test-runner').",
        },
    },
    "required": ["team_name"],
}

DESCRIPTION = "Create a new swarm team with a lead agent for coordinated multi-agent work."


class TeamCreateTool(Tool):
    name: str = TEAM_CREATE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.swarm.team_helpers import (
            get_team_file_path, write_team_file, sanitize_name
        )

        team_name: str = sanitize_name(input_data["team_name"])
        description: str = input_data.get("description") or ""
        agent_type: str = input_data.get("agent_type") or "general"

        lead_agent_id = f"agent-{secrets.token_hex(6)}"
        team_file_path = get_team_file_path(team_name)

        team_data = {
            "team_name": team_name,
            "description": description,
            "agent_type": agent_type,
            "lead_agent_id": lead_agent_id,
            "agents": [{"id": lead_agent_id, "role": "lead", "type": agent_type}],
        }
        try:
            await write_team_file(team_name, team_data)
        except Exception as exc:
            return [{"type": "text", "text": f"Error creating team: {exc}"}]

        result = {
            "team_name": team_name,
            "team_file_path": team_file_path,
            "lead_agent_id": lead_agent_id,
        }
        return [{"type": "text", "text": json.dumps(result)}]


team_create_tool = TeamCreateTool()
