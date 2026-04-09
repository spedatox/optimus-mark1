"""
Permission mode cycling logic for the Shift+Tab handler.
Mirrors src/utils/permissions/getNextPermissionMode.ts
"""
from __future__ import annotations

import os
from typing import Any

from optimus.types.permissions import PermissionMode, ToolPermissionContext

__all__ = [
    "get_next_permission_mode",
    "cycle_permission_mode",
]


def _can_cycle_to_auto(ctx: ToolPermissionContext) -> bool:
    """Returns True if we can cycle to auto mode."""
    if not ctx.is_auto_mode_available:
        return False
    try:
        from optimus.utils.permissions.permission_setup import is_auto_mode_gate_enabled

        gate_enabled = is_auto_mode_gate_enabled()
    except Exception:
        gate_enabled = False
    return bool(ctx.is_auto_mode_available) and gate_enabled


def get_next_permission_mode(
    tool_permission_context: ToolPermissionContext,
    team_context: Any | None = None,
) -> PermissionMode:
    """Determines the next permission mode when cycling through modes with Shift+Tab."""
    mode = tool_permission_context.mode

    if mode == "default":
        if os.environ.get("USER_TYPE") == "ant":
            if tool_permission_context.is_bypass_permissions_mode_available:
                return "bypassPermissions"
            if _can_cycle_to_auto(tool_permission_context):
                return "auto"
            return "default"
        return "acceptEdits"

    if mode == "acceptEdits":
        return "plan"

    if mode == "plan":
        if tool_permission_context.is_bypass_permissions_mode_available:
            return "bypassPermissions"
        if _can_cycle_to_auto(tool_permission_context):
            return "auto"
        return "default"

    if mode == "bypassPermissions":
        if _can_cycle_to_auto(tool_permission_context):
            return "auto"
        return "default"

    if mode == "dontAsk":
        return "default"

    # auto and any future modes → default
    return "default"


def cycle_permission_mode(
    tool_permission_context: ToolPermissionContext,
    team_context: Any | None = None,
) -> tuple[PermissionMode, ToolPermissionContext]:
    """Computes the next permission mode and returns (next_mode, updated_context).

    Handles context cleanup needed for the target mode (e.g., stripping
    dangerous permissions when entering auto mode).
    """
    from optimus.utils.permissions.permission_setup import transition_permission_mode

    next_mode = get_next_permission_mode(tool_permission_context, team_context)
    new_context = transition_permission_mode(
        tool_permission_context.mode, next_mode, tool_permission_context
    )
    return next_mode, new_context
