"""MCPTool — base class for dynamically-constructed MCP server tool wrappers."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult


class MCPToolBase(Tool):
    """
    Base for MCP-backed tool wrappers. The MCP client (services/mcp.py)
    creates instances of this class at connection time, overriding name,
    description, and input_schema with values from the server's tool manifest.
    """

    name: str = "mcp"
    description: str = "MCP tool — details provided by connected server."
    input_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": True,
    }

    # Set by MCP client after construction
    _server_name: str = ""
    _mcp_tool_name: str = ""

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        # MCP tools use passthrough permission — the MCP server enforces its own auth
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.services.mcp import get_mcp_manager

        manager = get_mcp_manager()
        try:
            result = await manager.call_tool(
                server=self._server_name,
                tool_name=self._mcp_tool_name,
                arguments=input_data,
            )
        except Exception as exc:
            return [{"type": "text", "text": f"MCP tool error: {exc}"}]

        # result may be a list of content blocks or a plain string
        if isinstance(result, list):
            return result
        return [{"type": "text", "text": json.dumps(result) if not isinstance(result, str) else result}]


def make_mcp_tool(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
) -> MCPToolBase:
    """Factory used by the MCP client to build a concrete tool wrapper."""
    tool = MCPToolBase()
    tool.name = tool_name
    tool.description = description
    tool.input_schema = input_schema
    tool._server_name = server_name
    tool._mcp_tool_name = tool_name
    return tool
