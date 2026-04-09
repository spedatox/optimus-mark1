"""ReadMcpResourceTool — read a resource from a connected MCP server by URI."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

READ_MCP_RESOURCE_TOOL_NAME = "ReadMcpResource"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "server": {
            "type": "string",
            "description": "The MCP server name.",
        },
        "uri": {
            "type": "string",
            "description": "The resource URI to read.",
        },
    },
    "required": ["server", "uri"],
}

DESCRIPTION = "Read a resource from a connected MCP server by URI."


class ReadMcpResourceTool(Tool):
    name: str = READ_MCP_RESOURCE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.services.mcp import get_mcp_manager

        server: str = input_data["server"]
        uri: str = input_data["uri"]
        manager = get_mcp_manager()

        try:
            contents = await manager.read_resource(server=server, uri=uri)
        except Exception as exc:
            return [{"type": "text", "text": f"Error reading resource: {exc}"}]

        result = {"contents": contents}
        return [{"type": "text", "text": json.dumps(result)}]


read_mcp_resource_tool = ReadMcpResourceTool()
