"""
Shared infrastructure for classifier-based permission systems.
Mirrors src/utils/permissions/classifierShared.ts
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "extract_tool_use_block",
    "parse_classifier_response",
]


def extract_tool_use_block(content: list[dict[str, Any]], tool_name: str) -> dict[str, Any] | None:
    """Extract tool use block from message content by tool name."""
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return block
    return None


def parse_classifier_response(tool_use_block: dict[str, Any], validate_fn: Any) -> Any | None:
    """Parse and validate classifier response from tool use block.

    validate_fn should be a callable that returns (success, data) or raises.
    Returns None if parsing fails.
    """
    try:
        return validate_fn(tool_use_block.get("input", {}))
    except Exception:
        return None
