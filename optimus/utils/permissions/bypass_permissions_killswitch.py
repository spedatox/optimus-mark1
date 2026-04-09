"""
Bypass permissions killswitch and auto-mode gate checks.
Mirrors src/utils/permissions/bypassPermissionsKillswitch.ts

React hooks (useKickOff*) are omitted — they are UI-layer concerns
handled by the Textual TUI in optimus. The async check functions are
ported faithfully.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from optimus.types.permissions import ToolPermissionContext

if TYPE_CHECKING:
    pass

__all__ = [
    "check_and_disable_bypass_permissions_if_needed",
    "reset_bypass_permissions_check",
    "check_and_disable_auto_mode_if_needed",
    "reset_auto_mode_gate_check",
]

_bypass_permissions_check_ran: bool = False
_auto_mode_check_ran: bool = False


async def check_and_disable_bypass_permissions_if_needed(
    tool_permission_context: ToolPermissionContext,
    set_app_state: Callable[[Any], None],
) -> None:
    """Checks if bypassPermissions should be disabled via Statsig gate.
    Runs only once per session (first query).
    """
    global _bypass_permissions_check_ran

    if _bypass_permissions_check_ran:
        return
    _bypass_permissions_check_ran = True

    if not tool_permission_context.is_bypass_permissions_mode_available:
        return

    try:
        from optimus.utils.permissions.permission_setup import should_disable_bypass_permissions

        should_disable = await should_disable_bypass_permissions()
    except Exception:
        should_disable = False

    if not should_disable:
        return

    try:
        from optimus.utils.permissions.permission_setup import create_disabled_bypass_permissions_context

        def updater(prev: Any) -> Any:
            new_ctx = create_disabled_bypass_permissions_context(prev.tool_permission_context)
            return type(prev)(**{**vars(prev), "tool_permission_context": new_ctx})

        set_app_state(updater)
    except Exception:
        pass


def reset_bypass_permissions_check() -> None:
    """Reset the run-once flag. Call after /login so the gate check re-runs."""
    global _bypass_permissions_check_ran
    _bypass_permissions_check_ran = False


async def check_and_disable_auto_mode_if_needed(
    tool_permission_context: ToolPermissionContext,
    set_app_state: Callable[[Any], None],
    fast_mode: bool | None = None,
) -> None:
    """Checks if auto mode should be disabled via GrowthBook.
    Runs only once per session (or until reset).
    """
    global _auto_mode_check_ran

    if _auto_mode_check_ran:
        return
    _auto_mode_check_ran = True

    try:
        from optimus.utils.permissions.permission_setup import verify_auto_mode_gate_access

        update_context_fn, notification = await verify_auto_mode_gate_access(
            tool_permission_context, fast_mode
        )

        def updater(prev: Any) -> Any:
            next_ctx = update_context_fn(prev.tool_permission_context)
            if next_ctx is prev.tool_permission_context and notification is None:
                return prev
            new_state = type(prev)(**{**vars(prev), "tool_permission_context": next_ctx})
            if notification:
                notifications = getattr(new_state, "notifications", None)
                if notifications is not None:
                    # Append notification to queue
                    queue = list(getattr(notifications, "queue", []))
                    queue.append(
                        {
                            "key": "auto-mode-gate-notification",
                            "text": notification,
                            "color": "warning",
                            "priority": "high",
                        }
                    )
                    notifications = type(notifications)(**{**vars(notifications), "queue": queue})
                    new_state = type(new_state)(**{**vars(new_state), "notifications": notifications})
            return new_state

        set_app_state(updater)
    except Exception:
        pass


def reset_auto_mode_gate_check() -> None:
    """Reset the run-once flag. Call after /login so the gate check re-runs."""
    global _auto_mode_check_ran
    _auto_mode_check_ran = False
