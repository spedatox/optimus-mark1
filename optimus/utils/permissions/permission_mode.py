"""
Permission mode utilities.
Mirrors src/utils/permissions/PermissionMode.ts
"""
from __future__ import annotations

import os
from typing import Literal

from optimus.types.permissions import (
    EXTERNAL_PERMISSION_MODES,
    PERMISSION_MODES,
    ExternalPermissionMode,
    PermissionMode,
)

# Re-export for backwards compatibility
__all__ = [
    "EXTERNAL_PERMISSION_MODES",
    "PERMISSION_MODES",
    "ExternalPermissionMode",
    "PermissionMode",
    "is_external_permission_mode",
    "to_external_permission_mode",
    "permission_mode_from_string",
    "permission_mode_title",
    "is_default_mode",
    "permission_mode_short_title",
    "permission_mode_symbol",
    "get_mode_color",
]

PAUSE_ICON = "⏸"

ModeColorKey = Literal["text", "planMode", "permission", "autoAccept", "error", "warning"]


class _PermissionModeConfig:
    __slots__ = ("title", "short_title", "symbol", "color", "external")

    def __init__(
        self,
        title: str,
        short_title: str,
        symbol: str,
        color: ModeColorKey,
        external: ExternalPermissionMode,
    ) -> None:
        self.title = title
        self.short_title = short_title
        self.symbol = symbol
        self.color = color
        self.external = external


_PERMISSION_MODE_CONFIG: dict[PermissionMode, _PermissionModeConfig] = {
    "default": _PermissionModeConfig(
        title="Default",
        short_title="Default",
        symbol="",
        color="text",
        external="default",
    ),
    "plan": _PermissionModeConfig(
        title="Plan Mode",
        short_title="Plan",
        symbol=PAUSE_ICON,
        color="planMode",
        external="plan",
    ),
    "acceptEdits": _PermissionModeConfig(
        title="Accept edits",
        short_title="Accept",
        symbol="\u23f5\u23f5",
        color="autoAccept",
        external="acceptEdits",
    ),
    "bypassPermissions": _PermissionModeConfig(
        title="Bypass Permissions",
        short_title="Bypass",
        symbol="\u23f5\u23f5",
        color="error",
        external="bypassPermissions",
    ),
    "dontAsk": _PermissionModeConfig(
        title="Don't Ask",
        short_title="DontAsk",
        symbol="\u23f5\u23f5",
        color="error",
        external="dontAsk",
    ),
    "auto": _PermissionModeConfig(
        title="Auto mode",
        short_title="Auto",
        symbol="\u23f5\u23f5",
        color="warning",
        external="default",
    ),
}

_DEFAULT_CONFIG = _PERMISSION_MODE_CONFIG["default"]


def _get_mode_config(mode: PermissionMode) -> _PermissionModeConfig:
    return _PERMISSION_MODE_CONFIG.get(mode, _DEFAULT_CONFIG)


def is_external_permission_mode(mode: PermissionMode) -> bool:
    """Type guard: returns True when mode is an ExternalPermissionMode.
    'auto' is ant-only and excluded from external modes."""
    if os.environ.get("USER_TYPE") != "ant":
        return True
    return mode not in ("auto", "bubble")


def to_external_permission_mode(mode: PermissionMode) -> ExternalPermissionMode:
    return _get_mode_config(mode).external


def permission_mode_from_string(s: str) -> PermissionMode:
    if s in PERMISSION_MODES:
        return s  # type: ignore[return-value]
    return "default"


def permission_mode_title(mode: PermissionMode) -> str:
    return _get_mode_config(mode).title


def is_default_mode(mode: PermissionMode | None) -> bool:
    return mode is None or mode == "default"


def permission_mode_short_title(mode: PermissionMode) -> str:
    return _get_mode_config(mode).short_title


def permission_mode_symbol(mode: PermissionMode) -> str:
    return _get_mode_config(mode).symbol


def get_mode_color(mode: PermissionMode) -> ModeColorKey:
    return _get_mode_config(mode).color
