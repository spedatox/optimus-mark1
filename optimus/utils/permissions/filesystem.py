"""
File system path permission utilities.
Mirrors src/utils/permissions/filesystem.ts
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from functools import lru_cache
from os import sep
from os.path import (
    expanduser,
    isabs,
    join,
    normpath,
    realpath,
)
from pathlib import Path, PurePosixPath
from tempfile import gettempdir
from typing import Any

from optimus.types.permissions import (
    PermissionDecision,
    PermissionRule,
    PermissionRuleSource,
    ToolPermissionContext,
)

__all__ = [
    "DANGEROUS_FILES",
    "DANGEROUS_DIRECTORIES",
    "normalize_case_for_comparison",
    "get_claude_skill_scope",
    "relative_path",
    "to_posix_path",
    "is_claude_settings_path",
    "get_session_memory_dir",
    "get_session_memory_path",
    "is_scratchpad_enabled",
    "get_claude_temp_dir_name",
    "get_claude_temp_dir",
    "get_project_temp_dir",
    "get_scratchpad_dir",
    "check_path_safety_for_auto_edit",
    "all_working_directories",
    "path_in_allowed_working_path",
    "path_in_working_path",
    "normalize_patterns_to_path",
    "get_file_read_ignore_patterns",
    "matching_rule_for_input",
    "check_read_permission_for_tool",
    "check_editable_internal_path",
    "check_readable_internal_path",
]

DANGEROUS_FILES = (
    ".gitconfig",
    ".gitmodules",
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".zprofile",
    ".profile",
    ".ripgreprc",
    ".mcp.json",
    ".claude.json",
)

DANGEROUS_DIRECTORIES = (
    ".git",
    ".vscode",
    ".idea",
    ".claude",
)


def normalize_case_for_comparison(path: str) -> str:
    """Normalizes a path for case-insensitive comparison."""
    return path.lower()


def _get_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if "microsoft-standard" in (Path("/proc/version").read_text(errors="ignore") if Path("/proc/version").exists() else ""):
        return "wsl"
    return "unix"


_PLATFORM = _get_platform()


def get_claude_skill_scope(file_path: str) -> dict[str, str] | None:
    """Returns skill name and pattern if file_path is inside a .claude/skills/{name}/ directory."""
    from optimus.utils.path import expand_path

    absolute_path = expand_path(file_path)
    absolute_path_lower = normalize_case_for_comparison(absolute_path)

    try:
        from optimus.bootstrap.state import get_original_cwd
        original_cwd = get_original_cwd()
    except Exception:
        original_cwd = os.getcwd()

    bases = [
        {
            "dir": expand_path(join(original_cwd, ".claude", "skills")),
            "prefix": "/.claude/skills/",
        },
        {
            "dir": expand_path(join(expanduser("~"), ".claude", "skills")),
            "prefix": "~/.claude/skills/",
        },
    ]

    for base in bases:
        dir_path = base["dir"]
        prefix = base["prefix"]
        dir_lower = normalize_case_for_comparison(dir_path)
        for s in [sep, "/"]:
            if absolute_path_lower.startswith(dir_lower + s.lower()):
                rest = absolute_path[len(dir_path) + len(s):]
                slash = rest.find("/")
                bslash = rest.find("\\") if sep == "\\" else -1
                if slash == -1 and bslash == -1:
                    cut = -1
                elif slash == -1:
                    cut = bslash
                elif bslash == -1:
                    cut = slash
                else:
                    cut = min(slash, bslash)
                if cut <= 0:
                    return None
                skill_name = rest[:cut]
                if not skill_name or skill_name == "." or ".." in skill_name:
                    return None
                if re.search(r"[*?\[\]]", skill_name):
                    return None
                return {"skillName": skill_name, "pattern": prefix + skill_name + "/**"}
    return None


def relative_path(from_path: str, to_path: str) -> str:
    """Cross-platform relative path calculation that returns POSIX-style paths."""
    if _PLATFORM == "windows":
        from pathlib import PureWindowsPath
        try:
            return PurePosixPath(PureWindowsPath(to_path).relative_to(PureWindowsPath(from_path))).as_posix()
        except ValueError:
            return os.path.relpath(to_path, from_path).replace("\\", "/")
    try:
        return str(PurePosixPath(to_path).relative_to(from_path))
    except ValueError:
        return os.path.relpath(to_path, from_path)


def to_posix_path(path: str) -> str:
    """Converts a path to POSIX format for pattern matching."""
    if _PLATFORM == "windows":
        return path.replace("\\", "/")
    return path


def _get_settings_paths() -> list[str]:
    try:
        from optimus.utils.settings.constants import SETTING_SOURCES
        from optimus.utils.settings.settings import get_settings_file_path_for_source

        paths = []
        for source in SETTING_SOURCES:
            p = get_settings_file_path_for_source(source)
            if p:
                paths.append(p)
        return paths
    except Exception:
        return []


def is_claude_settings_path(file_path: str) -> bool:
    """Returns True if the file is a Claude settings file."""
    from optimus.utils.path import expand_path

    expanded = expand_path(file_path)
    normalized = normalize_case_for_comparison(expanded)
    norm_sep = sep.lower()
    if (
        normalized.endswith(f"{norm_sep}.claude{norm_sep}settings.json")
        or normalized.endswith(f"{norm_sep}.claude{norm_sep}settings.local.json")
    ):
        return True
    return any(
        normalize_case_for_comparison(sp) == normalized
        for sp in _get_settings_paths()
    )


def _is_claude_config_file_path(file_path: str) -> bool:
    if is_claude_settings_path(file_path):
        return True
    try:
        from optimus.bootstrap.state import get_original_cwd
        original_cwd = get_original_cwd()
    except Exception:
        original_cwd = os.getcwd()
    commands_dir = join(original_cwd, ".claude", "commands")
    agents_dir = join(original_cwd, ".claude", "agents")
    skills_dir = join(original_cwd, ".claude", "skills")
    return (
        path_in_working_path(file_path, commands_dir)
        or path_in_working_path(file_path, agents_dir)
        or path_in_working_path(file_path, skills_dir)
    )


def get_session_memory_dir() -> str:
    """Returns the session memory directory path for the current session."""
    try:
        from optimus.utils.cwd import get_cwd
        from optimus.bootstrap.state import get_session_id
        from optimus.utils.session_storage_portable import get_project_dir
        return join(get_project_dir(get_cwd()), get_session_id(), "session-memory") + sep
    except Exception:
        return join(os.getcwd(), "session-memory") + sep


def get_session_memory_path() -> str:
    """Returns the session memory file path for the current session."""
    return join(get_session_memory_dir(), "summary.md")


def _is_session_memory_path(absolute_path: str) -> bool:
    normalized = normpath(absolute_path)
    return normalized.startswith(get_session_memory_dir())


def _is_project_dir_path(absolute_path: str) -> bool:
    try:
        from optimus.utils.cwd import get_cwd
        from optimus.utils.session_storage_portable import get_project_dir
        project_dir = get_project_dir(get_cwd())
        normalized = normpath(absolute_path)
        return normalized == project_dir or normalized.startswith(project_dir + sep)
    except Exception:
        return False


def is_scratchpad_enabled() -> bool:
    """Returns True if the scratchpad directory feature is enabled."""
    return False  # Controlled by Statsig gate 'tengu_scratch'


def get_claude_temp_dir_name() -> str:
    """Returns the user-specific Claude temp directory name."""
    if _PLATFORM == "windows":
        return "claude"
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return f"claude-{uid}"


@lru_cache(maxsize=1)
def get_claude_temp_dir() -> str:
    """Returns the Claude temp directory path with symlinks resolved."""
    base_tmp = os.environ.get("CLAUDE_CODE_TMPDIR") or (
        gettempdir() if _PLATFORM == "windows" else "/tmp"
    )
    try:
        base_tmp = realpath(base_tmp)
    except Exception:
        pass
    return join(base_tmp, get_claude_temp_dir_name()) + sep


def get_project_temp_dir() -> str:
    """Returns the project temp directory path."""
    from optimus.utils.path import sanitize_path

    try:
        from optimus.bootstrap.state import get_original_cwd
        original_cwd = get_original_cwd()
    except Exception:
        original_cwd = os.getcwd()
    return join(get_claude_temp_dir(), sanitize_path(original_cwd)) + sep


def get_scratchpad_dir() -> str:
    """Returns the scratchpad directory path for the current session."""
    try:
        from optimus.bootstrap.state import get_session_id
        return join(get_project_temp_dir(), get_session_id(), "scratchpad")
    except Exception:
        return join(get_project_temp_dir(), "scratchpad")


def _is_scratchpad_path(absolute_path: str) -> bool:
    if not is_scratchpad_enabled():
        return False
    scratchpad_dir = get_scratchpad_dir()
    normalized = normpath(absolute_path)
    return normalized == scratchpad_dir or normalized.startswith(scratchpad_dir + sep)


def _is_dangerous_file_path_to_auto_edit(path: str) -> bool:
    from optimus.utils.path import expand_path

    absolute_path = expand_path(path)
    path_segments = absolute_path.split(sep)
    file_name = path_segments[-1] if path_segments else None

    # UNC paths
    if path.startswith("\\\\") or path.startswith("//"):
        return True

    # Check dangerous directories (case-insensitive)
    for i, segment in enumerate(path_segments):
        normalized_segment = normalize_case_for_comparison(segment)
        for d in DANGEROUS_DIRECTORIES:
            if normalized_segment != normalize_case_for_comparison(d):
                continue
            # Special case: .claude/worktrees/ is not dangerous
            if d == ".claude":
                next_segment = path_segments[i + 1] if i + 1 < len(path_segments) else None
                if next_segment and normalize_case_for_comparison(next_segment) == "worktrees":
                    break
            return True

    # Check dangerous files (case-insensitive)
    if file_name:
        normalized_file_name = normalize_case_for_comparison(file_name)
        if any(normalize_case_for_comparison(f) == normalized_file_name for f in DANGEROUS_FILES):
            return True

    return False


def _has_suspicious_windows_path_pattern(path: str) -> bool:
    """Detect suspicious Windows path patterns that could bypass security."""
    if _PLATFORM in ("windows", "wsl"):
        colon_index = path.find(":", 2)
        if colon_index != -1:
            return True
    if re.search(r"~\d", path):
        return True
    if (
        path.startswith("\\\\?\\")
        or path.startswith("\\\\.\\")
        or path.startswith("//?/")
        or path.startswith("//./")
    ):
        return True
    if re.search(r"[.\s]+$", path):
        return True
    if re.search(r"\.(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", path, re.IGNORECASE):
        return True
    if re.search(r"(^|/|\\)\.{3,}(/|\\|$)", path):
        return True
    # UNC paths
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    return False


def check_path_safety_for_auto_edit(
    path: str, precomputed_paths_to_check: list[str] | None = None
) -> dict[str, Any]:
    """Checks if a path is safe for auto-editing. Returns dict with 'safe' key."""
    paths_to_check = precomputed_paths_to_check or _get_paths_for_permission_check(path)

    for p in paths_to_check:
        if _has_suspicious_windows_path_pattern(p):
            return {
                "safe": False,
                "message": f"Claude requested permissions to write to {path}, which contains a suspicious Windows path pattern that requires manual approval.",
                "classifierApprovable": False,
            }

    for p in paths_to_check:
        if _is_claude_config_file_path(p):
            return {
                "safe": False,
                "message": f"Claude requested permissions to write to {path}, but you haven't granted it yet.",
                "classifierApprovable": True,
            }

    for p in paths_to_check:
        if _is_dangerous_file_path_to_auto_edit(p):
            return {
                "safe": False,
                "message": f"Claude requested permissions to edit {path} which is a sensitive file.",
                "classifierApprovable": True,
            }

    return {"safe": True}


def _get_paths_for_permission_check(path: str) -> list[str]:
    """Returns the original path and its resolved symlink path (deduped)."""
    paths: list[str] = [path]
    try:
        resolved = realpath(path)
        if resolved not in paths:
            paths.append(resolved)
    except Exception:
        pass
    return paths


def all_working_directories(context: ToolPermissionContext) -> set[str]:
    """Returns all directories in scope for the permission context."""
    try:
        from optimus.bootstrap.state import get_original_cwd
        original_cwd = get_original_cwd()
    except Exception:
        original_cwd = os.getcwd()
    dirs = {original_cwd}
    dirs.update(context.additional_working_directories.keys())
    return dirs


@lru_cache(maxsize=256)
def _get_resolved_working_dir_paths(working_path: str) -> tuple[str, ...]:
    return tuple(_get_paths_for_permission_check(working_path))


def path_in_allowed_working_path(
    path: str,
    tool_permission_context: ToolPermissionContext,
    precomputed_paths_to_check: list[str] | None = None,
) -> bool:
    """Returns True if the path is within any allowed working directory."""
    paths_to_check = precomputed_paths_to_check or _get_paths_for_permission_check(path)
    working_paths: list[str] = []
    for wp in all_working_directories(tool_permission_context):
        working_paths.extend(_get_resolved_working_dir_paths(wp))

    return all(
        any(path_in_working_path(p, wp) for wp in working_paths)
        for p in paths_to_check
    )


def path_in_working_path(path: str, working_path: str) -> bool:
    """Returns True if path is inside (or equals) working_path."""
    from optimus.utils.path import expand_path, contains_path_traversal

    absolute_path = expand_path(path)
    absolute_working_path = expand_path(working_path)

    # Handle macOS common symlink patterns
    normalized_path = re.sub(r"^/private/var/", "/var/", absolute_path)
    normalized_path = re.sub(r"^/private/tmp(/|$)", r"/tmp\1", normalized_path)
    normalized_working = re.sub(r"^/private/var/", "/var/", absolute_working_path)
    normalized_working = re.sub(r"^/private/tmp(/|$)", r"/tmp\1", normalized_working)

    case_path = normalize_case_for_comparison(normalized_path)
    case_working = normalize_case_for_comparison(normalized_working)

    rel = relative_path(case_working, case_path)

    if rel == "":
        return True
    if contains_path_traversal(rel):
        return False
    # Path is inside (relative path that doesn't go up)
    return not PurePosixPath(rel).is_absolute()


def _root_path_for_source(source: PermissionRuleSource) -> str:
    from optimus.utils.path import expand_path

    try:
        from optimus.bootstrap.state import get_original_cwd
        original_cwd = get_original_cwd()
    except Exception:
        original_cwd = os.getcwd()

    if source in ("cliArg", "command", "session"):
        return expand_path(original_cwd)
    try:
        from optimus.utils.settings.settings import get_settings_root_path_for_source
        return get_settings_root_path_for_source(source)
    except Exception:
        return expand_path(original_cwd)


def _pattern_with_root(pattern: str, source: PermissionRuleSource) -> tuple[str, str | None]:
    """Returns (relative_pattern, root) for a gitignore-style pattern.
    root=None means the pattern can match anywhere.
    """
    dir_sep = "/"
    if pattern.startswith(dir_sep + dir_sep):
        pattern_without_double = pattern[1:]
        if _PLATFORM == "windows" and re.match(r"^/[a-z]/", pattern_without_double, re.IGNORECASE):
            drive_letter = pattern_without_double[1].upper()
            path_after_drive = pattern_without_double[2:]
            drive_root = f"{drive_letter}:\\"
            rel = path_after_drive.lstrip("/")
            return rel, drive_root
        return pattern_without_double, dir_sep
    elif pattern.startswith("~/"):
        return pattern[1:], expanduser("~")
    elif pattern.startswith(dir_sep):
        return pattern, _root_path_for_source(source)

    normalized = pattern[2:] if pattern.startswith("./") else pattern
    return normalized, None


def _get_patterns_by_root(
    tool_permission_context: ToolPermissionContext,
    tool_type: str,  # 'edit' | 'read'
    behavior: str,  # 'allow' | 'deny' | 'ask'
) -> dict[str | None, dict[str, PermissionRule]]:
    """Returns {root: {pattern: rule}} mapping."""
    from optimus.utils.permissions.permissions import get_rule_by_contents_for_tool_name

    tool_name = "Edit" if tool_type == "edit" else "Read"
    rules = get_rule_by_contents_for_tool_name(tool_permission_context, tool_name, behavior)  # type: ignore[arg-type]

    patterns_by_root: dict[str | None, dict[str, PermissionRule]] = {}
    for pattern, rule in rules.items():
        rel_pattern, root = _pattern_with_root(pattern, rule.source)
        if root not in patterns_by_root:
            patterns_by_root[root] = {}
        patterns_by_root[root][rel_pattern] = rule
    return patterns_by_root


def normalize_patterns_to_path(
    patterns_by_root: dict[str | None, list[str]],
    root: str,
) -> list[str]:
    """Normalizes patterns to be relative to the given root."""
    result: set[str] = set()
    # null-root patterns match anywhere
    for p in (patterns_by_root.get(None) or []):
        result.add(p)

    for pattern_root, patterns in patterns_by_root.items():
        if pattern_root is None:
            continue
        for pattern in patterns:
            full_pattern = str(PurePosixPath(pattern_root) / pattern.lstrip("/"))
            if pattern_root == root:
                result.add("/" + pattern.lstrip("/"))
            elif full_pattern.startswith(root + "/"):
                rel = full_pattern[len(root):]
                result.add("/" + rel.lstrip("/"))
            else:
                try:
                    rel = str(PurePosixPath(pattern_root).relative_to(root))
                    if rel and not rel.startswith(".."):
                        result.add("/" + rel + "/" + pattern.lstrip("/"))
                except ValueError:
                    pass
    return list(result)


def get_file_read_ignore_patterns(
    tool_permission_context: ToolPermissionContext,
) -> dict[str | None, list[str]]:
    """Returns deny patterns for file read permissions, keyed by root."""
    patterns_by_root = _get_patterns_by_root(tool_permission_context, "read", "deny")
    return {root: list(pattern_map.keys()) for root, pattern_map in patterns_by_root.items()}


def matching_rule_for_input(
    path: str,
    tool_permission_context: ToolPermissionContext,
    tool_type: str,
    behavior: str,
) -> PermissionRule | None:
    """Returns the first matching rule for the given path, or None."""
    import fnmatch

    from optimus.utils.path import expand_path

    try:
        from optimus.utils.cwd import get_cwd
        cwd = get_cwd()
    except Exception:
        cwd = os.getcwd()

    file_abs = expand_path(path)
    if _PLATFORM == "windows":
        file_abs = file_abs.replace("\\", "/")

    patterns_by_root = _get_patterns_by_root(tool_permission_context, tool_type, behavior)

    for root, pattern_map in patterns_by_root.items():
        effective_root = root if root is not None else cwd
        # Ensure POSIX format for relative path comparison
        if _PLATFORM == "windows":
            effective_root = effective_root.replace("\\", "/")

        # Compute relative path
        try:
            rel = str(PurePosixPath(file_abs).relative_to(effective_root))
        except ValueError:
            # Path is outside of this root
            continue

        if not rel:
            continue

        for pattern, rule in pattern_map.items():
            adj_pattern = pattern
            # Strip /** suffix (like TS version) — directory itself is included
            if adj_pattern.endswith("/**"):
                adj_pattern = adj_pattern[:-3]

            # Use fnmatch-style matching on the relative path
            if _gitignore_match(rel, adj_pattern):
                # Map pattern back to rule (check for /** variant)
                with_wildcard = pattern + "/**"
                if with_wildcard in pattern_map:
                    return pattern_map[with_wildcard]
                return rule

    return None


def _gitignore_match(path: str, pattern: str) -> bool:
    """Simple gitignore-style pattern matching."""
    import fnmatch

    # Leading slash means anchored to root
    anchored = pattern.startswith("/")
    p = pattern.lstrip("/")

    # Check direct match
    if fnmatch.fnmatch(path, p):
        return True
    # Directory prefix match (pattern matches parent dir)
    if fnmatch.fnmatch(path.split("/")[0] if "/" in path else path, p):
        return True
    # Allow path to be inside matched directory
    if fnmatch.fnmatch(path, p + "/*"):
        return True
    if fnmatch.fnmatch(path, p + "/**"):
        return True
    # If not anchored, check any path component
    if not anchored:
        parts = path.split("/")
        for i in range(len(parts)):
            subpath = "/".join(parts[i:])
            if fnmatch.fnmatch(subpath, p):
                return True
    return False


def check_editable_internal_path(path: str, context: dict) -> dict[str, Any]:
    """Returns {'behavior': 'allow', ...} if path is an internal editable path."""
    norm = normpath(path)

    # Session memory paths are editable
    if _is_session_memory_path(path):
        return {"behavior": "allow", "decisionReason": {"type": "other", "reason": "Session memory path"}}

    # Scratchpad paths are editable
    if _is_scratchpad_path(path):
        return {"behavior": "allow", "decisionReason": {"type": "other", "reason": "Scratchpad path"}}

    return {"behavior": "ask"}


def check_readable_internal_path(path: str, context: dict) -> dict[str, Any]:
    """Returns {'behavior': 'allow', ...} if path is an internal readable path."""
    # Project temp dir and session memory are readable
    if _is_project_dir_path(path):
        return {"behavior": "allow", "decisionReason": {"type": "other", "reason": "Project temp dir path"}}

    if _is_session_memory_path(path):
        return {"behavior": "allow", "decisionReason": {"type": "other", "reason": "Session memory path"}}

    if _is_scratchpad_path(path):
        return {"behavior": "allow", "decisionReason": {"type": "other", "reason": "Scratchpad path"}}

    return {"behavior": "ask"}


def check_read_permission_for_tool(
    tool: Any,
    input_data: dict[str, Any],
    tool_permission_context: ToolPermissionContext,
) -> PermissionDecision:
    """Returns the permission decision for a read operation."""
    from optimus.utils.permissions.path_validation import validate_path, FileOperationType

    get_path_fn = getattr(tool, "get_path", None)
    if not callable(get_path_fn):
        return _ask_permission(tool.name, "read")

    path = get_path_fn(input_data)
    try:
        from optimus.utils.cwd import get_cwd
        cwd = get_cwd()
    except Exception:
        cwd = os.getcwd()

    result = validate_path(path, cwd, tool_permission_context, "read")
    if result.allowed:
        return _allow_decision(input_data)
    return _ask_permission(tool.name, "read", result.resolved_path)


def _allow_decision(input_data: dict) -> Any:
    from optimus.types.permissions import PermissionAllowDecision
    return PermissionAllowDecision(updated_input=input_data)


def _ask_permission(tool_name: str, op: str, path: str | None = None) -> Any:
    from optimus.types.permissions import PermissionAskDecision
    msg = f"Claude requested permissions to {op} {'from ' + path if path else 'using ' + tool_name}, but you haven't granted it yet."
    return PermissionAskDecision(message=msg)
