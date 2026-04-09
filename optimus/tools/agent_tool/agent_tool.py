"""
AgentTool — launch a sub-agent to handle complex tasks.
Mirrors src/tools/AgentTool/AgentTool.tsx (core launch + run logic; UI/React omitted).
"""
from __future__ import annotations
import uuid
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

AGENT_TOOL_NAME = "Agent"
LEGACY_AGENT_TOOL_NAME = "Task"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The task for the agent to perform.",
        },
        "description": {
            "type": "string",
            "description": "Short (3-5 word) description of what the agent will do.",
        },
        "subagent_type": {
            "type": "string",
            "description": (
                "Optional specialized agent type. "
                "Available: 'general-purpose', 'Explore', 'Plan'."
            ),
        },
    },
    "required": ["prompt"],
}

DESCRIPTION = """\
Launch a new agent to handle complex, multi-step tasks autonomously.

When to use:
- Tasks that require 10+ tool calls
- Independent research or exploration that can run in parallel
- Long-running tasks that shouldn't block the main conversation

The agent has access to the same tools as the parent agent.
Returns the agent's final response when complete.
"""

# System prompts per agent type
_AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "Explore": (
        "You are a fast exploration agent. Your job is to quickly explore codebases, "
        "find files, search for patterns, and answer questions about code structure. "
        "Be thorough but efficient. Return your findings as a clear summary."
    ),
    "Plan": (
        "You are a software architect agent. Your job is to design implementation plans, "
        "identify critical files, and consider architectural trade-offs. "
        "Return step-by-step plans with clear rationale."
    ),
    "general-purpose": (
        "You are a general-purpose agent. Complete the given task using the available tools. "
        "Be precise and thorough. Return results clearly."
    ),
}

_DEFAULT_SYSTEM = (
    "You are an autonomous agent. Complete the given task using the available tools. "
    "Be precise and thorough. Return your results clearly."
)


class AgentTool(Tool):
    name: str = AGENT_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.query import query
        from optimus.tool import ToolUseContext as TUC

        prompt: str = input_data["prompt"]
        subagent_type: str = input_data.get("subagent_type") or "general-purpose"

        system = _AGENT_SYSTEM_PROMPTS.get(subagent_type, _DEFAULT_SYSTEM)

        # Sub-agent gets its own context with a fresh session ID
        sub_ctx = TUC(
            session_id=str(uuid.uuid4()),
            cwd=ctx.cwd,
            permission_mode=ctx.permission_mode,
        )

        # Import tools lazily to avoid circular imports
        from optimus.tools import get_all_tools
        tools = get_all_tools()

        messages = [{"role": "user", "content": prompt}]
        output_parts: list[str] = []

        async for event in await query(
            messages=messages,
            system=system,
            tools=tools,
            tool_use_context=sub_ctx,
        ):
            etype = event.get("type")
            if etype == "stream_text":
                output_parts.append(event["text"])
            elif etype == "error":
                return [{"type": "text", "text": f"Agent error: {event['error']}"}]

        result = "".join(output_parts).strip()
        return [{"type": "text", "text": result or "(agent completed with no output)"}]


agent_tool = AgentTool()
