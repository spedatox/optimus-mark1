"""
Current working directory management with per-async-context overrides.
Mirrors src/utils/cwd.ts

Uses contextvars (Python's AsyncLocalStorage equivalent) to allow concurrent
agents to each see their own working directory without interfering.
"""
from __future__ import annotations

from contextvars import ContextVar

# Per-async-context CWD override (None = use global state)
_cwd_override: ContextVar[str | None] = ContextVar("_cwd_override", default=None)


def run_with_cwd_override(cwd: str, fn: Any) -> Any:
    """
    Run `fn` with an overridden working directory for the current async context.
    All calls to pwd()/get_cwd() within fn (and its async descendants) will
    return `cwd` instead of the global one.
    """
    token = _cwd_override.set(cwd)
    try:
        return fn()
    finally:
        _cwd_override.reset(token)


async def run_with_cwd_override_async(cwd: str, coro: Any) -> Any:
    """Async variant of run_with_cwd_override."""
    token = _cwd_override.set(cwd)
    try:
        return await coro
    finally:
        _cwd_override.reset(token)


def pwd() -> str:
    """Return the current working directory for this async context."""
    override = _cwd_override.get()
    if override is not None:
        return override
    from optimus.bootstrap.state import get_cwd_state
    return get_cwd_state()


def get_cwd() -> str:
    """Return the current working directory, falling back to original cwd."""
    try:
        return pwd()
    except Exception:
        from optimus.bootstrap.state import get_original_cwd
        return get_original_cwd()


# Avoid circular import at module level
from typing import Any  # noqa: E402
