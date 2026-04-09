"""
AI-powered permission explanation generator.
Mirrors src/utils/permissions/permissionExplainer.ts
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from optimus.types.permissions import PermissionExplanation, RiskLevel

__all__ = [
    "is_permission_explainer_enabled",
    "generate_permission_explanation",
]

_SYSTEM_PROMPT = "Analyze shell commands and explain what they do, why you're running them, and potential risks."

_EXPLAIN_COMMAND_TOOL = {
    "name": "explain_command",
    "description": "Provide an explanation of a shell command",
    "input_schema": {
        "type": "object",
        "properties": {
            "explanation": {
                "type": "string",
                "description": "What this command does (1-2 sentences)",
            },
            "reasoning": {
                "type": "string",
                "description": 'Why YOU are running this command. Start with "I" - e.g. "I need to check the file contents"',
            },
            "risk": {
                "type": "string",
                "description": "What could go wrong, under 15 words",
            },
            "riskLevel": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH"],
                "description": "LOW (safe dev workflows), MEDIUM (recoverable changes), HIGH (dangerous/irreversible)",
            },
        },
        "required": ["explanation", "reasoning", "risk", "riskLevel"],
    },
}


def is_permission_explainer_enabled() -> bool:
    """Returns True if the permission explainer feature is enabled."""
    try:
        from optimus.utils.config import get_global_config

        config = get_global_config()
        return getattr(config, "permission_explainer_enabled", True) is not False
    except Exception:
        return True


def _format_tool_input(input_data: Any) -> str:
    if isinstance(input_data, str):
        return input_data
    try:
        return json.dumps(input_data, indent=2, ensure_ascii=False)
    except Exception:
        return str(input_data)


def _extract_conversation_context(messages: list[Any], max_chars: int = 1000) -> str:
    """Extract recent conversation context from messages."""
    assistant_messages = [m for m in messages if getattr(m, "type", None) == "assistant"]
    assistant_messages = assistant_messages[-3:]

    context_parts: list[str] = []
    total_chars = 0

    for msg in reversed(assistant_messages):
        content = getattr(msg, "message", None)
        if content is None:
            continue
        blocks = getattr(content, "content", [])
        text_blocks = " ".join(
            b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
            for b in blocks
            if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "text"
        )
        if text_blocks and total_chars < max_chars:
            remaining = max_chars - total_chars
            truncated = text_blocks[:remaining] + ("..." if len(text_blocks) > remaining else "")
            context_parts.insert(0, truncated)
            total_chars += len(truncated)

    return "\n\n".join(context_parts)


async def generate_permission_explanation(
    tool_name: str,
    tool_input: Any,
    tool_description: str | None = None,
    messages: list[Any] | None = None,
    signal: Any = None,
) -> PermissionExplanation | None:
    """Generate a permission explanation using the AI model.

    Returns None if the feature is disabled, request is aborted, or an error occurs.
    """
    if not is_permission_explainer_enabled():
        return None

    start_time = time.monotonic()

    try:
        from optimus.utils.side_query import side_query

        formatted_input = _format_tool_input(tool_input)
        conversation_context = _extract_conversation_context(messages or [])

        user_prompt = (
            f"Tool: {tool_name}\n"
            + (f"Description: {tool_description}\n" if tool_description else "")
            + f"Input:\n{formatted_input}"
            + (f"\n\nRecent conversation context:\n{conversation_context}" if conversation_context else "")
            + "\n\nExplain this command in context."
        )

        try:
            from optimus.utils.model.model import get_main_loop_model
            model = get_main_loop_model()
        except Exception:
            model = "claude-haiku-4-5"

        response = await side_query(
            model=model,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[_EXPLAIN_COMMAND_TOOL],
            tool_choice={"type": "tool", "name": "explain_command"},
            signal=signal,
            query_source="permission_explainer",
        )

        # Extract structured data from tool use block
        tool_use_block = next(
            (b for b in getattr(response, "content", []) if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"),
            None,
        )
        if tool_use_block is not None:
            input_data = tool_use_block.get("input", {}) if isinstance(tool_use_block, dict) else getattr(tool_use_block, "input", {})
            risk_level = input_data.get("riskLevel")
            explanation = input_data.get("explanation")
            reasoning = input_data.get("reasoning")
            risk = input_data.get("risk")
            if risk_level in ("LOW", "MEDIUM", "HIGH") and explanation and reasoning and risk:
                return PermissionExplanation(
                    risk_level=risk_level,  # type: ignore[arg-type]
                    explanation=explanation,
                    reasoning=reasoning,
                    risk=risk,
                )

        return None

    except Exception as exc:
        if signal is not None and getattr(signal, "aborted", False):
            return None
        return None
