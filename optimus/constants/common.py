"""
Common date/time utilities — port of ``src/constants/common.ts``.

Provides helpers for obtaining the current local date in formats suitable for
inclusion in system prompts and tool prompts.  The key design constraint is
**prompt-cache stability**: the session-start date is memoised so that it
doesn't change mid-session (which would bust the cached prefix).  A date
override env var (``CLAUDE_CODE_OVERRIDE_DATE``) is honoured for deterministic
testing.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache


def get_local_iso_date() -> str:
    """Return the current local date as an ISO-8601 ``YYYY-MM-DD`` string.

    If the ``CLAUDE_CODE_OVERRIDE_DATE`` environment variable is set its value
    is returned verbatim, allowing tests and automated runs to pin the date
    without changing the system clock.

    The implementation mirrors the TypeScript source: it uses the *local*
    timezone rather than UTC, matching the user's wall-clock date.

    Returns:
        Date string in ``YYYY-MM-DD`` format.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        return override

    today = date.today()
    return today.strftime("%Y-%m-%d")


@lru_cache(maxsize=1)
def _get_session_start_date_cached(override: str | None) -> str:
    """Inner cached implementation keyed on the override env var value.

    Separating the cache key from the body means that changing
    ``CLAUDE_CODE_OVERRIDE_DATE`` (common in tests) automatically yields a
    fresh result without manual cache invalidation.
    """
    if override:
        return override
    return date.today().strftime("%Y-%m-%d")


def get_session_start_date() -> str:
    """Return the session-start date as an ISO-8601 ``YYYY-MM-DD`` string.

    Unlike :func:`get_local_iso_date`, this function is memoised: the first
    call captures the date and all subsequent calls within the same process
    return the same value even if midnight rolls over.

    This mirrors ``memoize(getLocalISODate)`` (i.e. ``getSessionStartDate``) in
    the TypeScript source, which is used on the main interactive path via
    ``memoize(getUserContext)`` in ``context.ts``.  Simple/bare mode calls
    ``getSystemPrompt`` per-request and relies on this explicit memoised date to
    avoid busting the cached prefix at midnight.

    Returns:
        Date string in ``YYYY-MM-DD`` format, fixed at the time of first call.
    """
    return _get_session_start_date_cached(os.environ.get("CLAUDE_CODE_OVERRIDE_DATE"))


def get_local_month_year() -> str:
    """Return the current month and year as a human-readable string.

    Example output: ``"February 2026"``.

    Changes monthly rather than daily, reducing prompt-cache churn when this
    value is embedded in tool prompts.  Honours ``CLAUDE_CODE_OVERRIDE_DATE``
    for test determinism.

    Returns:
        String in ``"Month YYYY"`` format using the ``en-US`` locale month name.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        dt = datetime.fromisoformat(override)
    else:
        dt = datetime.now()

    # Use strftime for locale-independent English month names, matching the
    # TypeScript toLocaleString('en-US', { month: 'long', year: 'numeric' }).
    return dt.strftime("%B %Y")
