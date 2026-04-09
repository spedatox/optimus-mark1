"""GlobTool — fast file pattern matching. Mirrors src/tools/GlobTool/GlobTool.ts"""
from __future__ import annotations
import glob as _glob
import os
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

GLOB_TOOL_NAME = "Glob"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "The glob pattern to match files against."},
        "path": {"type": "string", "description": "Directory to search in. Defaults to current working directory."},
    },
    "required": ["pattern"],
}

DESCRIPTION = """\
Fast file pattern matching tool that works with any codebase size.
Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\".
Returns matching file paths sorted by modification time.
Use this tool when you need to find files by name patterns.
"""


class GlobTool(Tool):
    name: str = GLOB_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        pattern: str = input_data["pattern"]
        base = expand_path(input_data.get("path") or get_cwd(), get_cwd())

        full_pattern = os.path.join(base, pattern) if not os.path.isabs(pattern) else pattern

        try:
            matches = _glob.glob(full_pattern, recursive=True)
        except Exception as exc:
            return [{"type": "text", "text": f"Glob error: {exc}"}]

        # Sort by mtime descending (most-recently-modified first)
        def _mtime(p: str) -> float:
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0.0

        matches.sort(key=_mtime, reverse=True)

        if not matches:
            return [{"type": "text", "text": f"No files matched pattern: {pattern}"}]

        output = "\n".join(matches[:1000])
        if len(matches) > 1000:
            output += f"\n... ({len(matches) - 1000} more results)"
        return [{"type": "text", "text": output}]


glob_tool = GlobTool()
