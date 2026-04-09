"""
Shared utilities for shell-based tools.
Mirrors src/utils/shell/shellToolUtils.ts
"""
from __future__ import annotations

import os
import sys

from optimus.utils.env_utils import is_env_truthy, is_env_defined_falsy


SHELL_TOOL_NAMES: list[str] = ["Bash", "PowerShell"]


def is_powershell_tool_enabled() -> bool:
    """PowerShell tool is Windows-only; ants default on, external default off."""
    if sys.platform != "win32":
        return False
    if os.environ.get("USER_TYPE") == "ant":
        return not is_env_defined_falsy(os.environ.get("CLAUDE_CODE_USE_POWERSHELL_TOOL"))
    return is_env_truthy(os.environ.get("CLAUDE_CODE_USE_POWERSHELL_TOOL"))
