"""LSTool — directory listing. Mirrors src/tools/LSTool."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

LS_TOOL_NAME = "LS"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Absolute path to the directory to list."},
        "ignore": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of glob patterns to ignore.",
        },
    },
    "required": ["path"],
}

DESCRIPTION = """\
Lists files and directories in a given path.
The path parameter must be an absolute path.
Use this tool to explore directory structure.
"""


class LSTool(Tool):
    name: str = LS_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        import fnmatch
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        dir_path = expand_path(input_data["path"], get_cwd())
        ignore_patterns: list[str] = input_data.get("ignore") or []

        if not os.path.exists(dir_path):
            return [{"type": "text", "text": f"Directory not found: {dir_path}"}]
        if not os.path.isdir(dir_path):
            return [{"type": "text", "text": f"Not a directory: {dir_path}"}]

        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            return [{"type": "text", "text": f"Permission denied: {dir_path}"}]

        def should_ignore(name: str) -> bool:
            return any(fnmatch.fnmatch(name, pat) for pat in ignore_patterns)

        lines: list[str] = []
        for name in entries:
            if should_ignore(name):
                continue
            full = os.path.join(dir_path, name)
            suffix = "/" if os.path.isdir(full) else ""
            lines.append(f"{name}{suffix}")

        if not lines:
            return [{"type": "text", "text": f"(empty directory: {dir_path})"}]

        return [{"type": "text", "text": "\n".join(lines)}]


ls_tool = LSTool()
