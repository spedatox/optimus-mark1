"""SendMessageTool — send structured messages to peer agents in a swarm."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

SEND_MESSAGE_TOOL_NAME = "SendMessage"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "to": {
            "type": "string",
            "description": "Agent ID or name to send the message to.",
        },
        "message": {
            "type": "string",
            "description": "The message content to send.",
        },
        "message_type": {
            "type": "string",
            "enum": ["text", "shutdown_request", "shutdown_response", "plan_approval_response"],
            "description": "Type of message.",
            "default": "text",
        },
        "request_id": {
            "type": "string",
            "description": "Request ID for response messages.",
        },
        "approve": {
            "type": "boolean",
            "description": "For shutdown_response / plan_approval_response.",
        },
    },
    "required": ["to", "message"],
}

DESCRIPTION = """\
Send a message to another agent in the swarm. Used for agent-to-agent
communication including shutdown requests, plan approvals, and text messages.
"""


class SendMessageTool(Tool):
    name: str = SEND_MESSAGE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.swarm.mailbox import write_to_mailbox

        to: str = input_data["to"]
        message: str = input_data["message"]
        message_type: str = input_data.get("message_type", "text")
        request_id: str | None = input_data.get("request_id")
        approve: bool | None = input_data.get("approve")

        payload: dict[str, Any] = {
            "type": message_type,
            "content": message,
        }
        if request_id is not None:
            payload["request_id"] = request_id
        if approve is not None:
            payload["approve"] = approve

        try:
            await write_to_mailbox(to, payload)
            result = {"delivered": True, "to": to, "message_type": message_type}
        except Exception as exc:
            result = {"delivered": False, "to": to, "error": str(exc)}

        return [{"type": "text", "text": json.dumps(result)}]


send_message_tool = SendMessageTool()
