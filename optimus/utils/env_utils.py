"""
Environment-variable utilities — port of ``src/utils/envUtils.ts``.

Provides helpers for reading well-known Claude Code environment variables,
deriving configuration paths, and querying runtime mode flags (bare mode,
non-interactive mode, etc.).

All public functions mirror their TypeScript counterparts 1-to-1 in name
(converted to ``snake_case``), signature, and semantics.
"""
from __future__ import annotations

import os
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Truthy / falsy sentinel sets
# ---------------------------------------------------------------------------

_TRUTHY_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSY_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off"})

# ---------------------------------------------------------------------------
# Vertex region override table — mirrors VERTEX_REGION_OVERRIDES in envUtils.ts
# Order matters: more-specific prefixes must come before less-specific ones.
# ---------------------------------------------------------------------------

_VERTEX_REGION_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("claude-haiku-4-5", "VERTEX_REGION_CLAUDE_HAIKU_4_5"),
    ("claude-3-5-haiku", "VERTEX_REGION_CLAUDE_3_5_HAIKU"),
    ("claude-3-5-sonnet", "VERTEX_REGION_CLAUDE_3_5_SONNET"),
    ("claude-3-7-sonnet", "VERTEX_REGION_CLAUDE_3_7_SONNET"),
    ("claude-opus-4-1", "VERTEX_REGION_CLAUDE_4_1_OPUS"),
    ("claude-opus-4", "VERTEX_REGION_CLAUDE_4_0_OPUS"),
    ("claude-sonnet-4-6", "VERTEX_REGION_CLAUDE_4_6_SONNET"),
    ("claude-sonnet-4-5", "VERTEX_REGION_CLAUDE_4_5_SONNET"),
    ("claude-sonnet-4", "VERTEX_REGION_CLAUDE_4_0_SONNET"),
)


# ---------------------------------------------------------------------------
# Config home directory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _get_claude_config_home_dir_cached(cache_key: str | None) -> str:
    """Inner cached implementation — keyed on CLAUDE_CONFIG_DIR value.

    The ``cache_key`` parameter is intentionally the *value* of the env var so
    that changing the env var in tests (which is common) automatically busts the
    cache, matching the ``memoize(() => process.env.CLAUDE_CONFIG_DIR)`` resolver
    used in the TypeScript original.
    """
    raw = os.environ.get("CLAUDE_CONFIG_DIR")
    if raw:
        path = raw
    else:
        path = str(Path.home() / ".claude")
    # NFC normalisation mirrors String.prototype.normalize('NFC') in the source.
    return unicodedata.normalize("NFC", path)


def get_claude_config_home_dir() -> str:
    """Return the Claude configuration home directory.

    Reads ``CLAUDE_CONFIG_DIR`` from the environment; falls back to
    ``~/.claude``.  The result is NFC-normalised to match the TypeScript
    source behaviour and is memoised — keyed on the current value of
    ``CLAUDE_CONFIG_DIR`` — so tests that mutate the env var get a fresh value
    without needing to manually clear a cache.

    Returns:
        Absolute path string to the Claude config home directory.
    """
    return _get_claude_config_home_dir_cached(os.environ.get("CLAUDE_CONFIG_DIR"))


def get_teams_dir() -> str:
    """Return the path to the ``teams`` sub-directory of the config home.

    Returns:
        Absolute path string to ``<config_home>/teams``.
    """
    return str(Path(get_claude_config_home_dir()) / "teams")


# ---------------------------------------------------------------------------
# Boolean env-var helpers
# ---------------------------------------------------------------------------


def is_env_truthy(env_var: str | bool | None) -> bool:
    """Return ``True`` when *env_var* represents a truthy value.

    Accepts:
    - ``bool``: returned as-is.
    - ``str``: truthy when (after lowercasing and stripping) it is one of
      ``'1'``, ``'true'``, ``'yes'``, ``'on'``.
    - ``None`` / empty string / any falsy value: returns ``False``.

    Args:
        env_var: The environment-variable value (or a ``bool``) to test.

    Returns:
        ``True`` if the value is considered truthy, ``False`` otherwise.
    """
    if not env_var:
        return False
    if isinstance(env_var, bool):
        return env_var
    return env_var.lower().strip() in _TRUTHY_VALUES


def is_env_defined_falsy(env_var: str | bool | None) -> bool:
    """Return ``True`` when *env_var* is explicitly set to a falsy value.

    Unlike :func:`is_env_truthy`, this returns ``False`` for ``None`` (i.e. the
    variable being *absent* is not the same as being explicitly set to false).

    Accepts:
    - ``None``: returns ``False`` (variable is absent — not explicitly falsy).
    - ``bool``: returns ``not env_var``.
    - ``str``: falsy when (after lowercasing and stripping) it is one of
      ``'0'``, ``'false'``, ``'no'``, ``'off'``.  Empty string → ``False``.

    Args:
        env_var: The environment-variable value (or a ``bool``) to test.

    Returns:
        ``True`` if the value is explicitly falsy, ``False`` otherwise.
    """
    if env_var is None:
        return False
    if isinstance(env_var, bool):
        return not env_var
    if not env_var:
        # Empty string — not explicitly a falsy keyword.
        return False
    return env_var.lower().strip() in _FALSY_VALUES


# ---------------------------------------------------------------------------
# Runtime mode flags
# ---------------------------------------------------------------------------


def is_bare_mode() -> bool:
    """Return ``True`` when Claude Code is running in *bare* (simple) mode.

    Bare mode disables hooks, LSP, plugin sync, skill dir-walk, attribution,
    background prefetches, and **all** keychain/credential reads.  Auth is
    strictly ``ANTHROPIC_API_KEY`` env or ``apiKeyHelper`` from ``--settings``.
    Explicit CLI flags (``--plugin-dir``, ``--add-dir``, ``--mcp-config``) are
    still honoured.

    Checks both the ``CLAUDE_CODE_SIMPLE`` env var and ``--bare`` in
    ``sys.argv`` because several gates run before the CLI action handler has a
    chance to set the env var from the flag — notably the keychain prefetch that
    happens at process startup.

    Returns:
        ``True`` if bare mode is active.
    """
    return (
        is_env_truthy(os.environ.get("CLAUDE_CODE_SIMPLE"))
        or "--bare" in sys.argv
    )


def is_non_interactive_session() -> bool:
    """Return ``True`` when Claude Code is running in a non-interactive session.

    Non-interactive mode is signalled by setting the ``CLAUDE_NON_INTERACTIVE``
    environment variable to a truthy value (``1``, ``true``, ``yes``, ``on``).

    Returns:
        ``True`` if the session is non-interactive.
    """
    return is_env_truthy(os.environ.get("CLAUDE_NON_INTERACTIVE"))


def is_running_on_homespace() -> bool:
    """Return ``True`` when Claude Code is running on Homespace.

    Homespace is an Anthropic-internal cloud environment.  Requires both
    ``USER_TYPE=ant`` and ``COO_RUNNING_ON_HOMESPACE`` to be truthy.

    Returns:
        ``True`` if running on Homespace.
    """
    return os.environ.get("USER_TYPE") == "ant" and is_env_truthy(
        os.environ.get("COO_RUNNING_ON_HOMESPACE")
    )


def should_maintain_project_working_dir() -> bool:
    """Return ``True`` when bash commands should reset to the original working directory.

    Controlled by the ``CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`` env var.

    Returns:
        ``True`` if bash commands should maintain the project working directory.
    """
    return is_env_truthy(os.environ.get("CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"))


# ---------------------------------------------------------------------------
# Argument / option parsing helpers
# ---------------------------------------------------------------------------


def has_node_option(flag: str) -> bool:
    """Return ``True`` when *flag* appears as a discrete token in ``NODE_OPTIONS``.

    Splits on whitespace and checks for an exact token match to avoid false
    positives (e.g. ``--max-old-space-size`` matching ``--max-old``).

    Args:
        flag: The exact flag string to look for (e.g. ``'--inspect'``).

    Returns:
        ``True`` if the flag is present.
    """
    node_options = os.environ.get("NODE_OPTIONS", "")
    if not node_options:
        return False
    return flag in node_options.split()


def parse_env_vars(raw_env_args: list[str] | None) -> dict[str, str]:
    """Parse a list of ``KEY=VALUE`` strings into a dictionary.

    Args:
        raw_env_args: A list of strings in ``KEY=VALUE`` format, or ``None``.

    Returns:
        A dictionary mapping keys to values.

    Raises:
        ValueError: If any string does not contain ``=`` or has an empty key.
    """
    parsed: dict[str, str] = {}
    if raw_env_args:
        for env_str in raw_env_args:
            parts = env_str.split("=", 1)
            if len(parts) < 2 or not parts[0]:
                raise ValueError(
                    f"Invalid environment variable format: {env_str!r}, "
                    "environment variables should be added as: "
                    "-e KEY1=value1 -e KEY2=value2"
                )
            key, value = parts
            parsed[key] = value
    return parsed


# ---------------------------------------------------------------------------
# AWS / Vertex region helpers
# ---------------------------------------------------------------------------


def get_aws_region() -> str:
    """Return the AWS region, falling back to ``us-east-1``.

    Checks ``AWS_REGION`` then ``AWS_DEFAULT_REGION``, mirroring the Anthropic
    Bedrock SDK's own region resolution logic.

    Returns:
        AWS region string.
    """
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def get_default_vertex_region() -> str:
    """Return the default Vertex AI region.

    Reads ``CLOUD_ML_REGION`` from the environment; falls back to
    ``'us-east5'``.

    Returns:
        Vertex AI region string.
    """
    return os.environ.get("CLOUD_ML_REGION") or "us-east5"


def get_vertex_region_for_model(model: str | None) -> str:
    """Return the Vertex AI region appropriate for *model*.

    Walks the prefix table (``_VERTEX_REGION_OVERRIDES``) in order; the first
    matching prefix wins and its associated env var is read.  Falls back to
    :func:`get_default_vertex_region` when the env var is unset or when no
    prefix matches.

    Args:
        model: The model identifier string, or ``None``.

    Returns:
        Vertex AI region string.
    """
    if model:
        for prefix, env_name in _VERTEX_REGION_OVERRIDES:
            if model.startswith(prefix):
                return os.environ.get(env_name) or get_default_vertex_region()
    return get_default_vertex_region()
