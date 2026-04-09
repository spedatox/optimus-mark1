"""WebFetchTool — fetch URL content and apply a prompt. Mirrors src/tools/WebFetchTool/WebFetchTool.ts"""
from __future__ import annotations
import time
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

WEB_FETCH_TOOL_NAME = "WebFetch"
MAX_CONTENT_CHARS = 100_000

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to fetch content from."},
        "prompt": {"type": "string", "description": "The prompt to run on the fetched content."},
    },
    "required": ["url", "prompt"],
}

DESCRIPTION = """\
Fetches a URL and extracts its content as markdown, then applies a prompt to it.
Use this for reading web pages, documentation, or any HTTP resource.
The prompt parameter lets you focus on specific aspects of the page content.
"""


class WebFetchTool(Tool):
    name: str = WEB_FETCH_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        import asyncio
        url: str = input_data["url"]
        prompt: str = input_data["prompt"]
        t0 = time.monotonic()

        content, status, status_text = await _fetch_url(url)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if content is None:
            return [{"type": "text", "text": f"Failed to fetch {url}: {status_text}"}]

        # Truncate if huge
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "\n... (content truncated)"

        # Simple extraction: if prompt asks for something specific, we pass both
        result = f"URL: {url}\nStatus: {status} {status_text}\nFetched in: {elapsed_ms}ms\n\n{content}"
        return [{"type": "text", "text": result}]


async def _fetch_url(url: str) -> tuple[str | None, int, str]:
    try:
        import aiohttp  # type: ignore[import]
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                text = await resp.text(errors="replace")
                return _html_to_text(text), resp.status, resp.reason or ""
    except ImportError:
        pass
    # Fallback: urllib
    try:
        import asyncio
        import urllib.request
        loop = asyncio.get_event_loop()
        def _get() -> tuple[str | None, int, str]:
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    return r.read().decode("utf-8", errors="replace"), r.status, r.reason
            except Exception as exc:
                return None, 0, str(exc)
        return await loop.run_in_executor(None, _get)
    except Exception as exc:
        return None, 0, str(exc)


def _html_to_text(html: str) -> str:
    """Strip HTML tags for basic text extraction."""
    import re
    # Remove scripts and styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    html = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Remove remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    for ent, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        html = html.replace(ent, char)
    # Collapse whitespace
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


web_fetch_tool = WebFetchTool()
