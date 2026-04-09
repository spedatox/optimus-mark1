"""FileWriteTool — write/overwrite files. Mirrors src/tools/FileWriteTool/FileWriteTool.ts"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

FILE_WRITE_TOOL_NAME = "Write"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Absolute path to the file to write."},
        "content": {"type": "string", "description": "The content to write to the file."},
    },
    "required": ["file_path", "content"],
}

DESCRIPTION = """\
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- For modifying existing files, prefer the Edit tool.
- The file_path must be an absolute path.
- NEVER create documentation files (*.md) or README files unless explicitly requested.
"""


class FileWriteTool(Tool):
    name: str = FILE_WRITE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        from optimus.utils.permissions.filesystem import check_path_safety_for_auto_edit
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd
        abs_path = expand_path(input_data["file_path"], get_cwd())
        ok = check_path_safety_for_auto_edit(abs_path, get_cwd())
        if not ok:
            return ValidationResult(allowed=False, message=f"Path not allowed: {abs_path}", needs_prompt=True)
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        abs_path = expand_path(input_data["file_path"], get_cwd())
        content: str = input_data["content"]

        try:
            p = Path(abs_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as exc:
            return [{"type": "text", "text": f"Error writing file: {exc}"}]

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return [{"type": "text", "text": f"Written {lines} line(s) to {abs_path}"}]


file_write_tool = FileWriteTool()
