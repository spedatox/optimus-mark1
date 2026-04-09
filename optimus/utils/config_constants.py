"""
Configuration constants — kept dependency-free to avoid circular imports.
Mirrors src/utils/configConstants.ts
"""
from __future__ import annotations

from typing import Literal

NOTIFICATION_CHANNELS: tuple[str, ...] = (
    "auto",
    "iterm2",
    "iterm2_with_bell",
    "terminal_bell",
    "kitty",
    "ghostty",
    "notifications_disabled",
)

# Valid editor modes (excludes deprecated 'emacs', auto-migrated to 'normal')
EDITOR_MODES: tuple[str, ...] = ("normal", "vim")

# Valid teammate modes for spawning
TEAMMATE_MODES: tuple[str, ...] = ("auto", "tmux", "in-process")

NotificationChannel = Literal[
    "auto",
    "iterm2",
    "iterm2_with_bell",
    "terminal_bell",
    "kitty",
    "ghostty",
    "notifications_disabled",
]

EditorModeValue = Literal["normal", "vim"]
TeammateModeValue = Literal["auto", "tmux", "in-process"]
