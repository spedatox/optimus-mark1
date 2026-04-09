"""
Feature flag system — replaces ``import { feature } from 'bun:bundle'`` in TypeScript.

In Bun, ``feature()`` is a compile-time dead-code elimination mechanism that the
bundler replaces with a boolean literal, allowing tree-shaking of disabled code
paths at build time.  In Python there is no equivalent compile-time mechanism, so
we implement it as a runtime environment-variable check.  The semantics are
intentionally kept identical: callers write ``if feature('FLAG_NAME'): ...`` and
the body is executed only when the flag is enabled.

Usage::

    from optimus.utils.features import feature

    if feature('AGENT_TRIGGERS'):
        ...  # only runs when CLAUDE_AGENT_TRIGGERS=1 (or true/yes/on)
"""
from __future__ import annotations

import os

# Mapping from Bun bundle feature flag names to their corresponding environment
# variable names.  The env-var names mirror what the original TypeScript source
# uses (either directly or via --define substitution in the build pipeline).
_FEATURE_ENV_MAP: dict[str, str] = {
    "AGENT_TRIGGERS": "CLAUDE_AGENT_TRIGGERS",
    "AGENT_TRIGGERS_REMOTE": "CLAUDE_AGENT_TRIGGERS_REMOTE",
    "COORDINATOR_MODE": "CLAUDE_COORDINATOR_MODE",
    "PROACTIVE": "CLAUDE_PROACTIVE",
    "KAIROS": "CLAUDE_KAIROS",
    "KAIROS_PUSH_NOTIFICATION": "CLAUDE_KAIROS_PUSH_NOTIFICATION",
    "KAIROS_GITHUB_WEBHOOKS": "CLAUDE_KAIROS_GITHUB_WEBHOOKS",
    "MONITOR_TOOL": "CLAUDE_MONITOR_TOOL",
    "WORKFLOW_SCRIPTS": "CLAUDE_WORKFLOW_SCRIPTS",
    "TRANSCRIPT_CLASSIFIER": "CLAUDE_TRANSCRIPT_CLASSIFIER",
    "OVERFLOW_TEST_TOOL": "CLAUDE_OVERFLOW_TEST_TOOL",
    "CONTEXT_COLLAPSE": "CLAUDE_CONTEXT_COLLAPSE",
    "TERMINAL_PANEL": "CLAUDE_TERMINAL_PANEL",
    "WEB_BROWSER_TOOL": "CLAUDE_WEB_BROWSER_TOOL",
    "HISTORY_SNIP": "CLAUDE_HISTORY_SNIP",
    "UDS_INBOX": "CLAUDE_UDS_INBOX",
    "TOOL_SEARCH": "CLAUDE_TOOL_SEARCH",
}

_TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})


def feature(name: str) -> bool:
    """Return ``True`` when the named feature flag is enabled.

    The flag is considered enabled when the corresponding environment variable is
    set to one of ``1``, ``true``, ``yes``, or ``on`` (case-insensitive).

    For known flags the lookup uses the explicit mapping in ``_FEATURE_ENV_MAP``.
    For any unknown flag name the fallback env-var name is ``FEATURE_<NAME>``.

    Args:
        name: The feature flag name exactly as it appears in the original
              TypeScript source (e.g. ``'AGENT_TRIGGERS'``).

    Returns:
        ``True`` if the flag is enabled, ``False`` otherwise.
    """
    env_name = _FEATURE_ENV_MAP.get(name, f"FEATURE_{name}")
    raw = os.environ.get(env_name, "")
    return raw.lower().strip() in _TRUTHY_VALUES
