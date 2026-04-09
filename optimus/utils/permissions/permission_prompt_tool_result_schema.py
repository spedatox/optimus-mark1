"""
Schema and helpers for the MCP permission prompt tool result.
Mirrors src/utils/permissions/PermissionPromptToolResultSchema.ts
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "PermissionPromptInput",
    "PermissionAllowResult",
    "PermissionDenyResult",
    "PermissionPromptOutput",
    "permission_prompt_tool_result_to_permission_decision",
]


class PermissionPromptInput(BaseModel):
    """Input schema for the permission prompt tool."""

    tool_name: str = Field(description="The name of the tool requesting permission")
    input: dict[str, Any] = Field(description="The input for the tool")
    tool_use_id: str | None = Field(default=None, description="The unique tool use request ID")


class PermissionAllowResult(BaseModel):
    """Allow decision from the permission prompt tool."""

    behavior: str = "allow"
    updated_input: dict[str, Any] = Field(default_factory=dict)
    updated_permissions: list[Any] | None = None
    tool_use_id: str | None = None
    decision_classification: str | None = None


class PermissionDenyResult(BaseModel):
    """Deny decision from the permission prompt tool."""

    behavior: str = "deny"
    message: str
    interrupt: bool | None = None
    tool_use_id: str | None = None
    decision_classification: str | None = None


PermissionPromptOutput = PermissionAllowResult | PermissionDenyResult


def permission_prompt_tool_result_to_permission_decision(
    result: PermissionPromptOutput,
    tool: Any,
    input_data: dict[str, Any],
    tool_use_context: Any,
) -> Any:
    """Normalizes the result of a permission prompt tool to a PermissionDecision."""
    from optimus.types.permissions import (
        PermissionAllowDecision,
        PermissionDenyDecision,
    )
    from optimus.utils.permissions.permission_update import (
        apply_permission_updates,
        persist_permission_updates,
    )

    decision_reason = {
        "type": "permissionPromptTool",
        "permissionPromptToolName": tool.name,
        "toolResult": result.model_dump() if hasattr(result, "model_dump") else vars(result),
    }

    if result.behavior == "allow":
        updated_permissions = result.updated_permissions
        if updated_permissions:
            tool_use_context.set_app_state(
                lambda prev: type(prev)(
                    **{
                        **vars(prev),
                        "tool_permission_context": apply_permission_updates(
                            prev.tool_permission_context, updated_permissions
                        ),
                    }
                )
            )
            persist_permission_updates(updated_permissions)

        # Mobile clients send {} to satisfy schema — treat as "use original"
        updated_input = (
            result.updated_input
            if result.updated_input
            else input_data
        )
        return PermissionAllowDecision(
            updated_input=updated_input,
            decision_reason=decision_reason,
        )

    if result.behavior == "deny":
        if result.interrupt:
            if hasattr(tool_use_context, "abort_controller"):
                tool_use_context.abort_controller.abort()
        return PermissionDenyDecision(
            message=result.message,
            decision_reason=decision_reason,
        )

    # Fallback (shouldn't happen with validated input)
    return PermissionDenyDecision(
        message="Permission denied",
        decision_reason=decision_reason,
    )
