"""McpAuthTool — handle OAuth authentication flows for MCP servers."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

MCP_AUTH_TOOL_NAME = "McpAuth"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "server": {"type": "string", "description": "MCP server name to authenticate."},
        "action": {
            "type": "string",
            "enum": ["start", "complete", "status"],
            "description": "Authentication action.",
        },
        "code": {
            "type": "string",
            "description": "OAuth authorization code (for 'complete' action).",
        },
    },
    "required": ["server", "action"],
}

DESCRIPTION = "Manage OAuth authentication for MCP servers that require it."


class McpAuthTool(Tool):
    name: str = MCP_AUTH_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.services.mcp import get_mcp_manager

        server: str = input_data["server"]
        action: str = input_data["action"]
        code: str | None = input_data.get("code")

        manager = get_mcp_manager()
        try:
            if action == "start":
                auth_url = await manager.start_auth(server)
                result = {"status": "pending", "auth_url": auth_url, "server": server}
            elif action == "complete":
                if not code:
                    return [{"type": "text", "text": "Error: code required for complete."}]
                await manager.complete_auth(server, code)
                result = {"status": "authenticated", "server": server}
            elif action == "status":
                status = await manager.get_auth_status(server)
                result = {"status": status, "server": server}
            else:
                return [{"type": "text", "text": f"Unknown action: {action}"}]
        except Exception as exc:
            result = {"status": "error", "error": str(exc), "server": server}

        return [{"type": "text", "text": json.dumps(result)}]


mcp_auth_tool = McpAuthTool()
