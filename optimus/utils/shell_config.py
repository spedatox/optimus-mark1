"""
Shell configuration utilities — Python port of src/utils/shellConfig.ts

Manages shell config files (.bashrc, .zshrc, etc.) and provides shell
detection with memoization. On Windows, falls back to cmd.exe / PowerShell.

The TypeScript source (shellConfig.ts) focused on managing claude aliases in
shell config files. The Python port preserves that intent plus adds the
getShell() / shell detection logic referenced by other ported modules.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_ALIAS_REGEX = re.compile(r"^\s*alias\s+claude\s*=")

# ---------------------------------------------------------------------------
# Shell config path helpers
# ---------------------------------------------------------------------------


def get_shell_config_paths(
    env: dict[str, str | None] | None = None,
    homedir: str | None = None,
) -> dict[str, str]:
    """
    Return paths to shell configuration files, respecting ZDOTDIR for zsh.

    Mirrors getShellConfigPaths() from shellConfig.ts.

    Args:
        env: Optional env override (defaults to os.environ).
        homedir: Optional home directory override.

    Returns:
        Dict mapping shell names ('zsh', 'bash', 'fish') to config file paths.
    """
    home = homedir or str(Path.home())
    env_map: dict[str, str | None] = env if env is not None else dict(os.environ)

    zsh_config_dir = env_map.get("ZDOTDIR") or home

    return {
        "zsh": str(Path(zsh_config_dir) / ".zshrc"),
        "bash": str(Path(home) / ".bashrc"),
        "fish": str(Path(home) / ".config" / "fish" / "config.fish"),
    }


# ---------------------------------------------------------------------------
# Shell detection — getShell() equivalent
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_shell() -> str:
    """
    Detect the current shell executable path.

    Resolution order:
      1. CLAUDE_CODE_SHELL env var (explicit override)
      2. SHELL env var (Unix standard)
      3. Locate bash/zsh/sh on PATH
      4. Windows fallbacks: PowerShell > cmd.exe

    Returns:
        Absolute path to the shell executable.
    """
    explicit = os.environ.get("CLAUDE_CODE_SHELL")
    if explicit:
        return explicit

    shell_env = os.environ.get("SHELL")
    if shell_env and os.path.isabs(shell_env) and os.path.isfile(shell_env):
        return shell_env

    # Try to find common shells on PATH
    for candidate in ("bash", "zsh", "sh"):
        found = shutil.which(candidate)
        if found:
            return found

    # Windows fallbacks
    if sys.platform == "win32":
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh:
            return pwsh
        cmd = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "cmd.exe")
        if os.path.isfile(cmd):
            return cmd

    # Final fallback — /bin/sh almost always exists on Unix
    return "/bin/sh"


def get_shell_flags(shell_path: str) -> list[str]:
    """
    Return the appropriate flags for the given shell when spawning subprocesses.

    - bash/zsh/sh/fish: ['-c']  (command mode)
    - cmd.exe: ['/C']
    - powershell/pwsh: ['-Command']
    """
    name = Path(shell_path).stem.lower()
    if name in ("bash", "zsh", "sh", "fish", "dash", "ksh"):
        return ["-c"]
    if name == "cmd":
        return ["/C"]
    if name in ("powershell", "pwsh"):
        return ["-Command"]
    # Generic POSIX fallback
    return ["-c"]


def get_shell_rc_file(shell_path: str) -> str | None:
    """
    Return the rc file path for the given shell, or None if unknown.

    Used when we need to source the user's shell initialisation.
    """
    name = Path(shell_path).stem.lower()
    home = str(Path.home())
    mapping: dict[str, str] = {
        "bash": str(Path(home) / ".bashrc"),
        "zsh": str(Path(os.environ.get("ZDOTDIR", home)) / ".zshrc"),
        "fish": str(Path(home) / ".config" / "fish" / "config.fish"),
        "ksh": str(Path(home) / ".kshrc"),
        "dash": str(Path(home) / ".profile"),
    }
    return mapping.get(name)


# ---------------------------------------------------------------------------
# Alias management (mirrors shellConfig.ts functional exports)
# ---------------------------------------------------------------------------


def filter_claude_aliases(
    lines: list[str],
    installer_path: str | None = None,
) -> tuple[list[str], bool]:
    """
    Filter installer-created claude aliases from a list of config file lines.

    Only removes aliases pointing to ``installer_path`` (or the default local
    Claude path when *installer_path* is None).  Custom user aliases pointing
    elsewhere are preserved.

    Returns:
        (filtered_lines, had_alias) — the filtered list and whether our
        default installer alias was present.
    """
    if installer_path is None:
        installer_path = _get_local_claude_path()

    had_alias = False
    filtered: list[str] = []

    for line in lines:
        if CLAUDE_ALIAS_REGEX.search(line):
            # Try quoted form first
            m = re.search(r'alias\s+claude\s*=\s*["\']([^"\']+)["\']', line)
            if not m:
                m = re.search(r"alias\s+claude\s*=\s*([^#\n]+)", line)

            if m and m.group(1):
                target = m.group(1).strip()
                if installer_path and target == installer_path:
                    had_alias = True
                    continue  # Remove this line
        filtered.append(line)

    return filtered, had_alias


def _get_local_claude_path() -> str | None:
    """Return the default installer location for the claude binary, if known."""
    home = str(Path.home())
    candidate = str(Path(home) / ".claude" / "local" / "claude")
    return candidate if os.path.isfile(candidate) else None


def read_file_lines(file_path: str) -> list[str] | None:
    """
    Read a file and split it into lines.

    Returns None if the file does not exist or cannot be read.
    Mirrors readFileLines() from shellConfig.ts.
    """
    try:
        with open(file_path, encoding="utf-8") as fh:
            return fh.read().split("\n")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def write_file_lines(file_path: str, lines: list[str]) -> None:
    """
    Write lines back to a file, flushing to disk before close.

    Mirrors writeFileLines() from shellConfig.ts.
    """
    content = "\n".join(lines)
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())


def find_claude_alias(
    env: dict[str, str | None] | None = None,
    homedir: str | None = None,
) -> str | None:
    """
    Check if a claude alias exists in any shell config file.

    Returns the alias target string if found, None otherwise.
    Mirrors findClaudeAlias() from shellConfig.ts.
    """
    configs = get_shell_config_paths(env=env, homedir=homedir)

    for config_path in configs.values():
        lines = read_file_lines(config_path)
        if lines is None:
            continue

        for line in lines:
            if CLAUDE_ALIAS_REGEX.search(line):
                m = re.search(r"alias\s+claude=[\"']?([^\"'\s]+)", line)
                if m and m.group(1):
                    return m.group(1)

    return None


def find_valid_claude_alias(
    env: dict[str, str | None] | None = None,
    homedir: str | None = None,
) -> str | None:
    """
    Check if a claude alias exists and points to a valid executable.

    Returns the alias target if valid, None otherwise.
    Mirrors findValidClaudeAlias() from shellConfig.ts.
    """
    alias_target = find_claude_alias(env=env, homedir=homedir)
    if not alias_target:
        return None

    home = homedir or str(Path.home())

    # Expand ~ to home directory
    expanded = alias_target.replace("~", home, 1) if alias_target.startswith("~") else alias_target

    try:
        stat_result = Path(expanded).stat()
        # Check it's a regular file (or at least accessible)
        if Path(expanded).is_file() or Path(expanded).is_symlink():
            return alias_target
    except (FileNotFoundError, PermissionError, OSError):
        pass

    return None
