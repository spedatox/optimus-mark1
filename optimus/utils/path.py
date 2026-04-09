"""
Path expansion and normalization utilities.
Mirrors src/utils/path.ts
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def expand_path(path: str, base_dir: str | None = None) -> str:
    """
    Expand a path that may contain tilde notation to an absolute path.

    On Windows, POSIX-style paths (/c/Users/...) are converted to Windows
    format (C:\\Users\\...). Always returns paths in the native format.

    Raises TypeError for non-string inputs, ValueError for null bytes.
    """
    from optimus.utils.cwd import get_cwd

    actual_base_dir = base_dir if base_dir is not None else get_cwd()

    if not isinstance(path, str):
        raise TypeError(f"Path must be a string, received {type(path).__name__}")
    if not isinstance(actual_base_dir, str):
        raise TypeError(f"Base directory must be a string, received {type(actual_base_dir).__name__}")

    if "\0" in path or "\0" in actual_base_dir:
        raise ValueError("Path contains null bytes")

    trimmed = path.strip()
    if not trimmed:
        return str(Path(actual_base_dir).resolve())

    if trimmed == "~":
        return str(Path.home())

    if trimmed.startswith("~/"):
        return str(Path.home() / trimmed[2:])

    # On Windows, convert POSIX-style /c/Users/... to C:\Users\...
    processed = trimmed
    if sys.platform == "win32" and re.match(r"^/[a-zA-Z]/", trimmed):
        try:
            processed = _posix_path_to_windows_path(trimmed)
        except Exception:
            processed = trimmed

    if os.path.isabs(processed):
        return str(Path(processed).resolve())

    return str(Path(actual_base_dir) / processed)


def _posix_path_to_windows_path(posix_path: str) -> str:
    """Convert a POSIX-style path like /c/Users/foo to C:\\Users\\foo."""
    m = re.match(r"^/([a-zA-Z])(/.*)$", posix_path)
    if not m:
        return posix_path
    drive = m.group(1).upper()
    rest = m.group(2).replace("/", "\\")
    return f"{drive}:{rest}"


def to_relative_path(absolute_path: str) -> str:
    """
    Convert an absolute path to relative from cwd.
    If the path is outside cwd, returns the absolute path unchanged.
    """
    from optimus.utils.cwd import get_cwd
    try:
        rel = os.path.relpath(absolute_path, get_cwd())
        if rel.startswith(".."):
            return absolute_path
        return rel
    except ValueError:
        # On Windows, relpath raises ValueError for cross-drive paths
        return absolute_path


def get_directory_for_path(path: str) -> str:
    """
    Return the directory for a given path.
    If the path is a directory, returns it. Otherwise returns the parent.
    """
    absolute_path = expand_path(path)

    # SECURITY: Skip filesystem operations for UNC paths to prevent NTLM leaks
    if absolute_path.startswith("\\\\") or absolute_path.startswith("//"):
        return str(Path(absolute_path).parent)

    try:
        if Path(absolute_path).is_dir():
            return absolute_path
    except OSError:
        pass

    return str(Path(absolute_path).parent)


def contains_path_traversal(path: str) -> bool:
    """Check if a path contains directory traversal patterns (..)."""
    return bool(re.search(r"(?:^|[/\\])\.\.(?:[/\\]|$)", path))


def sanitize_path(name: str) -> str:
    """
    Make a string safe for use as a directory or file name.
    Replaces all non-alphanumeric characters with hyphens.
    For paths exceeding MAX_SANITIZED_LENGTH, truncates and appends a hash.
    """
    from optimus.utils.session_storage_portable import sanitize_path as _sp
    return _sp(name)


def normalize_path_for_config_key(path: str) -> str:
    """
    Normalize a path for use as a JSON config key.
    Resolves . and .. segments, then converts backslashes to forward slashes
    for consistent JSON serialization across platforms.
    """
    normalized = os.path.normpath(path)
    return normalized.replace("\\", "/")
