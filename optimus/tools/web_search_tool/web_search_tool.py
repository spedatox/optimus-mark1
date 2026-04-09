"""WebSearchTool — web search via Anthropic's web_search beta. Mirrors src/tools/WebSearchTool/WebSearchTool.ts"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

WEB_SEARCH_TOOL_NAME = "WebSearch"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to use."},
        "allowed_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of domains to restrict search results to.",
        },
        "blocked_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of domains to exclude from search results.",
        },
    },
    "required": ["query"],
}

DESCRIPTION = """\
Performs a web search and returns relevant results.
Use this when you need current information from the web.
The query should be a focused search string.
"""


class WebSearchTool(Tool):
    name: str = WEB_SEARCH_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        import anthropic

        query: str = input_data["query"]
        allowed_domains: list[str] | None = input_data.get("allowed_domains")
        blocked_domains: list[str] | None = input_data.get("blocked_domains")

        web_search_tool: dict[str, Any] = {"type": "web_search_20250305", "name": "web_search"}
        if allowed_domains:
            web_search_tool["allowed_domains"] = allowed_domains
        if blocked_domains:
            web_search_tool["blocked_domains"] = blocked_domains

        client = anthropic.AsyncAnthropic()
        try:
            resp = await client.beta.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                tools=[web_search_tool],  # type: ignore[list-item]
                messages=[{"role": "user", "content": query}],
                betas=["web-search-2025-03-05"],
            )
        except Exception as exc:
            return [{"type": "text", "text": f"Search failed: {exc}"}]

        # Extract text from response
        parts: list[str] = []
        for block in resp.content:
            if hasattr(block, "text"):
                parts.append(block.text)

        return [{"type": "text", "text": "\n\n".join(parts) or "No results found."}]


web_search_tool = WebSearchTool()
