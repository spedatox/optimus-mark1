"""BriefTool — send a message to the user (proactive or normal status update)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

BRIEF_TOOL_NAME = "Brief"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The message for the user. Supports markdown formatting.",
        },
        "attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional file paths to attach alongside the message.",
        },
        "status": {
            "type": "string",
            "enum": ["normal", "proactive"],
            "description": (
                "Use 'proactive' for unsolicited status updates or blockers. "
                "Use 'normal' when replying to something the user just said."
            ),
        },
    },
    "required": ["message", "status"],
}

DESCRIPTION = """\
Send a message to the user. Use this to surface task completion, blockers, or
status updates. Supports markdown. Optionally attach files.
"""


class BriefTool(Tool):
    name: str = BRIEF_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from pathlib import Path

        message: str = input_data["message"]
        status: str = input_data.get("status", "normal")
        attachment_paths: list[str] = input_data.get("attachments") or []

        resolved_attachments = []
        for path_str in attachment_paths:
            p = Path(path_str)
            if p.exists():
                resolved_attachments.append({
                    "path": str(p.resolve()),
                    "size": p.stat().st_size,
                    "isImage": p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"},
                })

        result = {
            "message": message,
            "status": status,
            "attachments": resolved_attachments if resolved_attachments else None,
            "sentAt": datetime.now(timezone.utc).isoformat(),
        }
        return [{"type": "text", "text": json.dumps(result)}]


brief_tool = BriefTool()
