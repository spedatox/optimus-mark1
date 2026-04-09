"""ListMcpResourcesTool — list resources from connected MCP servers."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

LIST_MCP_RESOURCES_TOOL_NAME = "ListMcpResources"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "server": {
            "type": "string",
            "description": "Optional server name to filter resources by.",
        },
    },
    "required": [],
}

DESCRIPTION = "List available resources from connected MCP servers."


class ListMcpResourcesTool(Tool):
    name: str = LIST_MCP_RESOURCES_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.services.mcp import get_mcp_manager

        server_filter: str | None = input_data.get("server")
        manager = get_mcp_manager()
        resources = await manager.list_resources(server_filter=server_filter)
        return [{"type": "text", "text": json.dumps(resources)}]


list_mcp_resources_tool = ListMcpResourcesTool()
