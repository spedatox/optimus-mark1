"""ToolSearchTool — fetch schemas for deferred tools by name or keyword query."""
from __future__ import annotations
import json
import re
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

TOOL_SEARCH_TOOL_NAME = "ToolSearch"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                'Query to find deferred tools. Use "select:<tool_name>" for direct '
                "selection, or keywords to search."
            ),
        },
        "max_results": {
            "type": "number",
            "description": "Maximum number of results to return (default: 5).",
            "default": 5,
        },
    },
    "required": ["query"],
}

DESCRIPTION = """\
Fetches full schema definitions for deferred tools so they can be called.
Use "select:<name>" to fetch by exact name, or provide keywords to search.
"""


def _score_tool(tool: Any, terms: list[str]) -> float:
    """Simple keyword scoring against tool name + description."""
    name = (tool.name or "").lower()
    desc = (tool.description or "").lower()
    score = 0.0
    for term in terms:
        if term in name:
            score += 2.0
        if term in desc:
            score += 1.0
    return score


class ToolSearchTool(Tool):
    name: str = TOOL_SEARCH_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.tools import get_all_tools

        query: str = input_data["query"]
        max_results: int = int(input_data.get("max_results") or 5)
        all_tools = get_all_tools()

        # Direct select mode
        if query.startswith("select:"):
            names = [n.strip() for n in query[len("select:"):].split(",") if n.strip()]
            matched = [t for t in all_tools if t.name in names]
        else:
            terms = [t.lower() for t in re.split(r"[\s,]+", query) if t]
            scored = [(t, _score_tool(t, terms)) for t in all_tools]
            scored.sort(key=lambda x: x[1], reverse=True)
            matched = [t for t, s in scored if s > 0][:max_results]

        schemas = []
        for tool in matched[:max_results]:
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            })

        result = {
            "matches": [s["name"] for s in schemas],
            "schemas": schemas,
            "query": query,
            "total_tools": len(all_tools),
        }
        return [{"type": "text", "text": json.dumps(result)}]


tool_search_tool = ToolSearchTool()
