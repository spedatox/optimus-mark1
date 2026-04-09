"""RemoteTriggerTool — manage scheduled remote agent triggers via the API."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

REMOTE_TRIGGER_TOOL_NAME = "RemoteTrigger"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["list", "get", "create", "update", "run"],
            "description": "Action to perform.",
        },
        "trigger_id": {
            "type": "string",
            "description": "Required for get, update, and run.",
        },
        "body": {
            "type": "object",
            "description": "JSON body for create and update.",
        },
    },
    "required": ["action"],
}

DESCRIPTION = "Manage scheduled remote agent triggers (list, get, create, update, run)."

_TRIGGERS_BETA = "ccr-triggers-2026-01-30"


class RemoteTriggerTool(Tool):
    name: str = REMOTE_TRIGGER_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        try:
            import aiohttp
        except ImportError:
            return [{"type": "text", "text": "Error: aiohttp is required for RemoteTrigger."}]

        from optimus.constants.oauth import get_oauth_config

        action: str = input_data["action"]
        trigger_id: str | None = input_data.get("trigger_id")
        body: dict | None = input_data.get("body")

        oauth_config = get_oauth_config()
        base_url = oauth_config.get("claudeAiApiUrl", "https://api.claude.ai")
        base = f"{base_url}/api/triggers"

        # Build URL and method
        if action == "list":
            url, method = base, "GET"
        elif action == "get":
            if not trigger_id:
                return [{"type": "text", "text": "Error: trigger_id required for get."}]
            url, method = f"{base}/{trigger_id}", "GET"
        elif action == "create":
            url, method = base, "POST"
        elif action == "update":
            if not trigger_id:
                return [{"type": "text", "text": "Error: trigger_id required for update."}]
            url, method = f"{base}/{trigger_id}", "PUT"
        elif action == "run":
            if not trigger_id:
                return [{"type": "text", "text": "Error: trigger_id required for run."}]
            url, method = f"{base}/{trigger_id}/run", "POST"
        else:
            return [{"type": "text", "text": f"Unknown action: {action}"}]

        async with aiohttp.ClientSession() as session:
            req_kwargs: dict[str, Any] = {"headers": {"anthropic-beta": _TRIGGERS_BETA}}
            if body and method in ("POST", "PUT"):
                req_kwargs["json"] = body
            async with session.request(method, url, **req_kwargs) as resp:
                status = resp.status
                try:
                    resp_json = await resp.json()
                except Exception:
                    resp_json = await resp.text()
                result = {"status": status, "json": json.dumps(resp_json)}

        return [{"type": "text", "text": json.dumps(result)}]


remote_trigger_tool = RemoteTriggerTool()
