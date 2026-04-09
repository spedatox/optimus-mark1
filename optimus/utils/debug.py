"""
Debug logging utilities.
Mirrors src/utils/debug.ts

Writes timestamped log lines to ~/.claude/debug/<session_id>.txt (or a
custom path via CLAUDE_CODE_DEBUG_LOGS_DIR / --debug-file=).
Debug mode is enabled by DEBUG / DEBUG_SDK env-vars or --debug / -d CLI flags.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from optimus.utils.debug_filter import DebugFilter, parse_debug_filter, should_show_debug_message

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

DebugLogLevel = Literal["verbose", "debug", "info", "warn", "error"]

_LEVEL_ORDER: dict[str, int] = {
    "verbose": 0,
    "debug": 1,
    "info": 2,
    "warn": 3,
    "error": 4,
}

# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

_runtime_debug_enabled: bool = False
_has_formatted_output: bool = False

# Simple in-memory buffer for the async (non-debug-mode) path
_pending_lines: list[str] = []
_flush_task: asyncio.Task | None = None  # type: ignore[type-arg]


def set_has_formatted_output(value: bool) -> None:
    global _has_formatted_output
    _has_formatted_output = value


def get_has_formatted_output() -> bool:
    return _has_formatted_output


# ---------------------------------------------------------------------------
# Memoized config readers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def get_min_debug_log_level() -> DebugLogLevel:
    raw = os.environ.get("CLAUDE_CODE_DEBUG_LOG_LEVEL", "").lower().strip()
    if raw in _LEVEL_ORDER:
        return raw  # type: ignore[return-value]
    return "debug"


@lru_cache(maxsize=None)
def is_debug_to_stderr() -> bool:
    return "--debug-to-stderr" in sys.argv or "-d2e" in sys.argv


@lru_cache(maxsize=None)
def get_debug_file_path() -> str | None:
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--debug-file="):
            return arg[len("--debug-file="):]
        if arg == "--debug-file" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


@lru_cache(maxsize=None)
def get_debug_filter() -> DebugFilter | None:
    for arg in sys.argv:
        if arg.startswith("--debug="):
            return parse_debug_filter(arg[len("--debug="):])
    return None


def is_debug_mode() -> bool:
    from optimus.utils.env_utils import is_env_truthy
    return (
        _runtime_debug_enabled
        or is_env_truthy(os.environ.get("DEBUG"))
        or is_env_truthy(os.environ.get("DEBUG_SDK"))
        or "--debug" in sys.argv
        or "-d" in sys.argv
        or any(a.startswith("--debug=") for a in sys.argv)
        or is_debug_to_stderr()
        or get_debug_file_path() is not None
    )


def enable_debug_logging() -> bool:
    """Enable debug logging at runtime (e.g. via /debug command).

    Returns True if logging was already active.
    """
    global _runtime_debug_enabled
    was_active = is_debug_mode() or os.environ.get("USER_TYPE") == "ant"
    _runtime_debug_enabled = True
    # Invalidate the lru_cache-backed checks (they don't depend on
    # _runtime_debug_enabled directly, so is_debug_mode() re-reads it each call)
    return was_active


# ---------------------------------------------------------------------------
# Log path
# ---------------------------------------------------------------------------

def get_debug_log_path() -> str:
    custom = get_debug_file_path()
    if custom:
        return custom
    env_dir = os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR")
    if env_dir:
        return env_dir
    from optimus.utils.env_utils import get_claude_config_home_dir
    from optimus.bootstrap.state import get_session_id
    return str(Path(get_claude_config_home_dir()) / "debug" / f"{get_session_id()}.txt")


# ---------------------------------------------------------------------------
# Symlink (best-effort)
# ---------------------------------------------------------------------------

_symlink_updated: bool = False


def _update_latest_debug_log_symlink() -> None:
    global _symlink_updated
    if _symlink_updated:
        return
    _symlink_updated = True
    try:
        log_path = Path(get_debug_log_path())
        latest = log_path.parent / "latest"
        try:
            latest.unlink()
        except OSError:
            pass
        try:
            latest.symlink_to(log_path)
        except (OSError, NotImplementedError):
            # Windows may not support symlinks without elevated privileges
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _should_log_debug_message(message: str) -> bool:
    if os.environ.get("NODE_ENV") == "test" and not is_debug_to_stderr():
        return False
    if os.environ.get("USER_TYPE") != "ant" and not is_debug_mode():
        return False
    filter_ = get_debug_filter()
    return should_show_debug_message(message, filter_)


# ---------------------------------------------------------------------------
# Core writer
# ---------------------------------------------------------------------------

def _write_line_sync(output: str) -> None:
    """Append a log line synchronously (used in debug mode and ants)."""
    log_path = Path(get_debug_log_path())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(output)
    _update_latest_debug_log_symlink()


async def _flush_buffer() -> None:
    global _pending_lines
    if not _pending_lines:
        return
    lines = _pending_lines[:]
    _pending_lines = []
    content = "".join(lines)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_line_sync, content)


async def _schedule_flush() -> None:
    await asyncio.sleep(1.0)
    await _flush_buffer()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_for_debugging(
    message: str,
    *,
    level: DebugLogLevel = "debug",
) -> None:
    """Write a timestamped debug message to the debug log.

    Silently drops the message when debug mode is off or the level is below
    the configured minimum.
    """
    if _LEVEL_ORDER.get(level, 1) < _LEVEL_ORDER.get(get_min_debug_log_level(), 1):
        return
    if not _should_log_debug_message(message):
        return

    if _has_formatted_output and "\n" in message:
        import json
        message = json.dumps(message)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    output = f"{timestamp} [{level.upper()}] {message.strip()}\n"

    if is_debug_to_stderr():
        sys.stderr.write(output)
        return

    if is_debug_mode():
        _write_line_sync(output)
    else:
        # Buffered path for ants without --debug
        global _flush_task
        _pending_lines.append(output)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running() and (_flush_task is None or _flush_task.done()):
                _flush_task = loop.create_task(_schedule_flush())
        except RuntimeError:
            pass


async def flush_debug_logs() -> None:
    """Flush any buffered debug log lines to disk."""
    await _flush_buffer()


def log_ant_error(context: str, error: Exception) -> None:
    """Log errors for ants only (always visible in production ant builds)."""
    if os.environ.get("USER_TYPE") != "ant":
        return
    if hasattr(error, "__traceback__") and error.__traceback__ is not None:
        import traceback
        stack = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log_for_debugging(f"[ANT-ONLY] {context} stack trace:\n{stack}", level="error")
