"""
File-system path validation for permission checks.
Mirrors src/utils/permissions/pathValidation.ts
"""
from __future__ import annotations

import os
import re
from os.path import (
    dirname,
    expanduser,
    isabs,
    normpath,
    realpath,
    sep,
)
from pathlib import Path
from typing import Any

from optimus.types.permissions import PermissionDecisionReason, ToolPermissionContext

__all__ = [
    "FileOperationType",
    "PathCheckResult",
    "ResolvedPathCheckResult",
    "format_directory_list",
    "get_glob_base_directory",
    "expand_tilde",
    "is_path_in_sandbox_write_allowlist",
    "is_path_allowed",
    "validate_glob_pattern",
    "is_dangerous_removal_path",
    "validate_path",
]

FileOperationType = str  # "read" | "write" | "create"

_GLOB_PATTERN_RE = re.compile(r"[*?\[\]{}]")
_MAX_DIRS_TO_LIST = 5
_WINDOWS_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:/?$")
_WINDOWS_DRIVE_CHILD_RE = re.compile(r"^[A-Za-z]:/[^/]+$")


class PathCheckResult:
    def __init__(self, allowed: bool, decision_reason: PermissionDecisionReason | None = None) -> None:
        self.allowed = allowed
        self.decision_reason = decision_reason


class ResolvedPathCheckResult(PathCheckResult):
    def __init__(
        self,
        allowed: bool,
        resolved_path: str,
        decision_reason: PermissionDecisionReason | None = None,
    ) -> None:
        super().__init__(allowed, decision_reason)
        self.resolved_path = resolved_path


def format_directory_list(directories: list[str]) -> str:
    """Format a list of directories for display."""
    count = len(directories)
    if count <= _MAX_DIRS_TO_LIST:
        return ", ".join(f"'{d}'" for d in directories)
    first = ", ".join(f"'{d}'" for d in directories[:_MAX_DIRS_TO_LIST])
    return f"{first}, and {count - _MAX_DIRS_TO_LIST} more"


def get_glob_base_directory(path: str) -> str:
    """Extracts the base directory from a glob pattern.
    For example: "/path/to/*.txt" returns "/path/to"
    """
    m = _GLOB_PATTERN_RE.search(path)
    if not m:
        return path
    before_glob = path[: m.start()]
    last_sep = max(before_glob.rfind("/"), before_glob.rfind("\\") if os.name == "nt" else -1)
    if last_sep == -1:
        return "."
    return before_glob[:last_sep] or "/"


def expand_tilde(path: str) -> str:
    """Expands ~ at the start of a path to the user's home directory.
    Only simple ~ and ~/ are expanded (not ~user, ~+, ~-).
    """
    if path == "~" or path.startswith("~/") or (os.name == "nt" and path.startswith("~\\")):
        return expanduser(path)
    return path


def is_path_in_sandbox_write_allowlist(resolved_path: str) -> bool:
    """Returns True if the path is in the sandbox write allowlist.
    Always returns False when sandboxing is not enabled (stub).
    """
    # Sandbox manager integration is deferred; return False by default
    return False


def _safe_resolve_path(path: str) -> tuple[str, bool]:
    """Returns (resolved_path, is_canonical).
    is_canonical is True when the path had no symlinks resolved.
    """
    try:
        resolved = realpath(path)
        is_canonical = resolved == normpath(path)
        return resolved, is_canonical
    except Exception:
        return normpath(path), False


def is_path_allowed(
    resolved_path: str,
    context: ToolPermissionContext,
    operation_type: FileOperationType,
    precomputed_paths_to_check: list[str] | None = None,
) -> PathCheckResult:
    """Checks if a resolved path is allowed for the given operation type."""
    from optimus.utils.permissions.filesystem import (
        check_editable_internal_path,
        check_path_safety_for_auto_edit,
        check_readable_internal_path,
        matching_rule_for_input,
        path_in_allowed_working_path,
    )

    permission_type = "read" if operation_type == "read" else "edit"

    # 1. Check deny rules first (they take precedence)
    deny_rule = matching_rule_for_input(resolved_path, context, permission_type, "deny")
    if deny_rule is not None:
        return PathCheckResult(
            allowed=False,
            decision_reason={"type": "rule", "rule": deny_rule},
        )

    # 2. For write/create operations, check internal editable paths
    if operation_type != "read":
        internal_edit = check_editable_internal_path(resolved_path, {})
        if internal_edit.get("behavior") == "allow":
            return PathCheckResult(allowed=True, decision_reason=internal_edit.get("decisionReason"))

    # 2.5. For write/create operations, check comprehensive safety validations
    if operation_type != "read":
        safety = check_path_safety_for_auto_edit(
            resolved_path, precomputed_paths_to_check
        )
        if not safety["safe"]:
            return PathCheckResult(
                allowed=False,
                decision_reason={
                    "type": "safetyCheck",
                    "reason": safety["message"],
                    "classifierApprovable": safety.get("classifierApprovable", False),
                },
            )

    # 3. Check if path is in allowed working directory
    in_working_dir = path_in_allowed_working_path(resolved_path, context, precomputed_paths_to_check)
    if in_working_dir:
        if operation_type == "read" or context.mode == "acceptEdits":
            return PathCheckResult(allowed=True)

    # 3.5. For read operations, check internal readable paths
    if operation_type == "read":
        internal_read = check_readable_internal_path(resolved_path, {})
        if internal_read.get("behavior") == "allow":
            return PathCheckResult(allowed=True, decision_reason=internal_read.get("decisionReason"))

    # 3.7. For write/create outside working directory, check sandbox write allowlist
    if operation_type != "read" and not in_working_dir and is_path_in_sandbox_write_allowlist(resolved_path):
        return PathCheckResult(
            allowed=True,
            decision_reason={"type": "other", "reason": "Path is in sandbox write allowlist"},
        )

    # 4. Check allow rules
    allow_rule = matching_rule_for_input(resolved_path, context, permission_type, "allow")
    if allow_rule is not None:
        return PathCheckResult(
            allowed=True,
            decision_reason={"type": "rule", "rule": allow_rule},
        )

    # 5. Not allowed
    return PathCheckResult(allowed=False)


def validate_glob_pattern(
    clean_path: str,
    cwd: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: FileOperationType,
) -> ResolvedPathCheckResult:
    """Validates a glob pattern by checking its base directory."""
    from optimus.utils.path import contains_path_traversal

    if contains_path_traversal(clean_path):
        abs_path = clean_path if isabs(clean_path) else os.path.join(cwd, clean_path)
        resolved_path, is_canonical = _safe_resolve_path(abs_path)
        result = is_path_allowed(
            resolved_path,
            tool_permission_context,
            operation_type,
            [resolved_path] if is_canonical else None,
        )
        return ResolvedPathCheckResult(
            allowed=result.allowed,
            resolved_path=resolved_path,
            decision_reason=result.decision_reason,
        )

    base_path = get_glob_base_directory(clean_path)
    abs_base = base_path if isabs(base_path) else os.path.join(cwd, base_path)
    resolved_path, is_canonical = _safe_resolve_path(abs_base)
    result = is_path_allowed(
        resolved_path,
        tool_permission_context,
        operation_type,
        [resolved_path] if is_canonical else None,
    )
    return ResolvedPathCheckResult(
        allowed=result.allowed,
        resolved_path=resolved_path,
        decision_reason=result.decision_reason,
    )


def is_dangerous_removal_path(resolved_path: str) -> bool:
    """Checks if a resolved path is dangerous for removal operations (rm/rmdir)."""
    forward_slashed = re.sub(r"[\\/]+", "/", resolved_path)

    if forward_slashed == "*" or forward_slashed.endswith("/*"):
        return True

    normalized = "/" if forward_slashed == "/" else forward_slashed.rstrip("/")

    if normalized == "/":
        return True

    if _WINDOWS_DRIVE_ROOT_RE.match(normalized):
        return True

    normalized_home = re.sub(r"[\\/]+", "/", expanduser("~"))
    if normalized == normalized_home:
        return True

    # Direct children of root
    parent = dirname(normalized)
    if parent == "/":
        return True

    if _WINDOWS_DRIVE_CHILD_RE.match(normalized):
        return True

    return False


def validate_path(
    path: str,
    cwd: str,
    tool_permission_context: ToolPermissionContext,
    operation_type: FileOperationType,
) -> ResolvedPathCheckResult:
    """Validates a file system path, handling tilde expansion and glob patterns."""
    # Remove surrounding quotes if present
    clean_path = expand_tilde(path.strip("'\""))

    # SECURITY: Block UNC paths that could leak credentials
    if clean_path.startswith("\\\\") or (
        len(clean_path) > 1
        and clean_path[0] == "/"
        and clean_path[1] == "/"
    ):
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=clean_path,
            decision_reason={"type": "other", "reason": "UNC network paths require manual approval"},
        )

    # SECURITY: Reject tilde variants (~user, ~+, ~-) that expand_tilde doesn't handle
    if clean_path.startswith("~"):
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=clean_path,
            decision_reason={
                "type": "other",
                "reason": "Tilde expansion variants (~user, ~+, ~-) in paths require manual approval",
            },
        )

    # SECURITY: Reject paths containing shell expansion syntax
    if "$" in clean_path or "%" in clean_path or clean_path.startswith("="):
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=clean_path,
            decision_reason={
                "type": "other",
                "reason": "Shell expansion syntax in paths requires manual approval",
            },
        )

    # SECURITY: Block glob patterns in write/create operations
    if _GLOB_PATTERN_RE.search(clean_path):
        if operation_type in ("write", "create"):
            return ResolvedPathCheckResult(
                allowed=False,
                resolved_path=clean_path,
                decision_reason={
                    "type": "other",
                    "reason": "Glob patterns are not allowed in write operations. Please specify an exact file path.",
                },
            )
        return validate_glob_pattern(clean_path, cwd, tool_permission_context, operation_type)

    # Resolve path
    abs_path = clean_path if isabs(clean_path) else os.path.join(cwd, clean_path)
    resolved_path, is_canonical = _safe_resolve_path(abs_path)

    result = is_path_allowed(
        resolved_path,
        tool_permission_context,
        operation_type,
        [resolved_path] if is_canonical else None,
    )
    return ResolvedPathCheckResult(
        allowed=result.allowed,
        resolved_path=resolved_path,
        decision_reason=result.decision_reason,
    )
