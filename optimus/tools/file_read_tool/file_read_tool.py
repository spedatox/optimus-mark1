"""FileReadTool — read files with optional line range. Mirrors src/tools/FileReadTool/FileReadTool.ts"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

FILE_READ_TOOL_NAME = "Read"
MAX_LINES_TO_READ = 2000
MAX_OUTPUT_CHARS = 200_000

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Absolute path to the file to read."},
        "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)."},
        "limit": {"type": "integer", "description": "Number of lines to read."},
    },
    "required": ["file_path"],
}

DESCRIPTION = """\
Reads a file from the local filesystem. You can access any file directly by using this tool.

Usage:
- The file_path parameter must be an absolute path, not a relative path.
- By default, it reads up to 2000 lines starting from the beginning of the file.
- When you already know which part of the file you need, only read that part.
- Results are returned with line numbers (cat -n format), starting at 1.
"""


class FileReadTool(Tool):
    name: str = FILE_READ_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        file_path: str = input_data["file_path"]
        offset: int = max(1, int(input_data.get("offset") or 1))
        limit: int = min(MAX_LINES_TO_READ, int(input_data.get("limit") or MAX_LINES_TO_READ))

        abs_path = expand_path(file_path, get_cwd())

        try:
            content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return [{"type": "text", "text": f"File not found: {abs_path}"}]
        except PermissionError:
            return [{"type": "text", "text": f"Permission denied: {abs_path}"}]
        except Exception as exc:
            return [{"type": "text", "text": f"Error reading file: {exc}"}]

        lines = content.splitlines(keepends=True)
        total = len(lines)
        start = offset - 1  # convert to 0-indexed
        end = min(start + limit, total)
        selected = lines[start:end]

        # Format with line numbers (cat -n style)
        numbered = "".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))

        if len(numbered) > MAX_OUTPUT_CHARS:
            numbered = numbered[:MAX_OUTPUT_CHARS] + "\n... (output truncated)"

        truncation_note = ""
        if end < total:
            truncation_note = f"\n\n(Showing lines {offset}–{end} of {total}. Use offset/limit to read more.)"

        return [{"type": "text", "text": numbered + truncation_note}]


file_read_tool = FileReadTool()
