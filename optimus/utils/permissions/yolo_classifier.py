"""
YOLO / auto-mode classifier stub.
Mirrors src/utils/permissions/yoloClassifier.ts (external/stub build).

The full classifier is ant-only (TRANSCRIPT_CLASSIFIER feature gate).
This module exposes the public surface area with disabled/stub implementations
so the rest of the codebase can import without crashing.
"""
from __future__ import annotations

import os
from typing import Any

from optimus.types.permissions import YoloClassifierResult

__all__ = [
    "YOLO_CLASSIFIER_TOOL_NAME",
    "AutoModeRules",
    "get_default_external_auto_mode_rules",
    "format_action_for_classifier",
    "classify_yolo_action",
]

YOLO_CLASSIFIER_TOOL_NAME = "yolo_classifier"


class AutoModeRules:
    """Shape of the settings.autoMode config — the three classifier prompt sections."""

    def __init__(
        self,
        allow: list[str] | None = None,
        soft_deny: list[str] | None = None,
        environment: list[str] | None = None,
    ) -> None:
        self.allow: list[str] = allow or []
        self.soft_deny: list[str] = soft_deny or []
        self.environment: list[str] = environment or []


def get_default_external_auto_mode_rules() -> AutoModeRules:
    """Returns default external auto mode rules. Returns empty rules in stub."""
    return AutoModeRules()


def format_action_for_classifier(tool_name: str, input_data: dict[str, Any]) -> str:
    """Formats a tool invocation as a string for the classifier."""
    import json

    try:
        input_str = json.dumps(input_data, ensure_ascii=False)
    except Exception:
        input_str = str(input_data)
    return f"{tool_name}: {input_str}"


async def classify_yolo_action(
    messages: list[Any],
    action: str,
    tools: Any,
    tool_permission_context: Any,
    signal: Any,
) -> YoloClassifierResult:
    """Classify an action in YOLO/auto mode. Always returns unavailable in stub."""
    return YoloClassifierResult(
        should_block=False,
        reason="Auto mode classifier is not available",
        model="",
        unavailable=True,
    )
