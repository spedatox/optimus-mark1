"""LSPTool — placeholder for Language Server Protocol integration."""
from __future__ import annotations
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

LSP_TOOL_NAME = "LSP"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "method": {"type": "string", "description": "LSP method to invoke."},
        "params": {"type": "object", "description": "LSP method parameters."},
    },
    "required": ["method"],
}

DESCRIPTION = "Invoke a Language Server Protocol method for code intelligence features."


class LSPTool(Tool):
    name: str = LSP_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        return [{"type": "text", "text": "LSP integration not yet implemented."}]


lsp_tool = LSPTool()
