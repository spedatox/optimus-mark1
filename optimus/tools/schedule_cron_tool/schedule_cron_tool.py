"""ScheduleCronTool — CronCreate, CronDelete, CronList for scheduled prompts."""
from __future__ import annotations
import json
import secrets
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

# ---------------------------------------------------------------------------
# In-memory cron job registry (session-scoped)
# ---------------------------------------------------------------------------
_cron_jobs: dict[str, dict[str, Any]] = {}


def _cron_to_human(expr: str) -> str:
    """Best-effort human description of a cron expression."""
    parts = expr.split()
    if len(parts) != 5:
        return expr
    minute, hour, dom, month, dow = parts
    if expr == "* * * * *":
        return "every minute"
    if minute.startswith("*/"):
        return f"every {minute[2:]} minutes"
    if hour == "*":
        return f"at minute {minute} of every hour"
    return f"at {hour}:{minute.zfill(2)}"


# ---------------------------------------------------------------------------
# CronCreateTool
# ---------------------------------------------------------------------------
CRON_CREATE_TOOL_NAME = "CronCreate"

CRON_CREATE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cron": {
            "type": "string",
            "description": 'Standard 5-field cron expression (e.g. "*/5 * * * *").',
        },
        "prompt": {
            "type": "string",
            "description": "The prompt to enqueue at each fire time.",
        },
        "recurring": {
            "type": "boolean",
            "description": "true (default) = fire every match; false = fire once then auto-delete.",
            "default": True,
        },
        "durable": {
            "type": "boolean",
            "description": "true = persist to disk; false (default) = in-memory only.",
            "default": False,
        },
    },
    "required": ["cron", "prompt"],
}


class CronCreateTool(Tool):
    name: str = CRON_CREATE_TOOL_NAME
    description: str = "Schedule a recurring or one-shot prompt using a cron expression."
    input_schema: dict[str, Any] = CRON_CREATE_INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        if len(_cron_jobs) >= 50:
            return [{"type": "text", "text": "Error: maximum of 50 cron jobs reached."}]

        cron: str = input_data["cron"]
        prompt: str = input_data["prompt"]
        recurring: bool = bool(input_data.get("recurring", True))
        durable: bool = bool(input_data.get("durable", False))

        job_id = secrets.token_hex(8)
        _cron_jobs[job_id] = {
            "id": job_id,
            "cron": cron,
            "prompt": prompt,
            "recurring": recurring,
            "durable": durable,
            "humanSchedule": _cron_to_human(cron),
        }

        result = {
            "id": job_id,
            "humanSchedule": _cron_to_human(cron),
            "recurring": recurring,
            "durable": durable,
        }
        return [{"type": "text", "text": json.dumps(result)}]


# ---------------------------------------------------------------------------
# CronDeleteTool
# ---------------------------------------------------------------------------
CRON_DELETE_TOOL_NAME = "CronDelete"

CRON_DELETE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Job ID returned by CronCreate.",
        },
    },
    "required": ["id"],
}


class CronDeleteTool(Tool):
    name: str = CRON_DELETE_TOOL_NAME
    description: str = "Cancel a scheduled cron job by ID."
    input_schema: dict[str, Any] = CRON_DELETE_INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        job_id: str = input_data["id"]
        if job_id not in _cron_jobs:
            return [{"type": "text", "text": f"Error: job '{job_id}' not found."}]
        del _cron_jobs[job_id]
        return [{"type": "text", "text": json.dumps({"id": job_id})}]


# ---------------------------------------------------------------------------
# CronListTool
# ---------------------------------------------------------------------------
CRON_LIST_TOOL_NAME = "CronList"

CRON_LIST_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}


class CronListTool(Tool):
    name: str = CRON_LIST_TOOL_NAME
    description: str = "List all active scheduled cron jobs."
    input_schema: dict[str, Any] = CRON_LIST_INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        jobs = list(_cron_jobs.values())
        result = {"jobs": jobs}
        return [{"type": "text", "text": json.dumps(result)}]


cron_create_tool = CronCreateTool()
cron_delete_tool = CronDeleteTool()
cron_list_tool = CronListTool()
