"""FileEditTool — exact string replacement in files. Mirrors src/tools/FileEditTool/FileEditTool.ts"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

FILE_EDIT_TOOL_NAME = "Edit"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Absolute path to the file to modify."},
        "old_string": {"type": "string", "description": "The text to replace (must be unique in the file)."},
        "new_string": {"type": "string", "description": "The text to replace it with."},
        "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)."},
    },
    "required": ["file_path", "old_string", "new_string"],
}

DESCRIPTION = """\
Performs exact string replacements in files.

Usage:
- The edit will FAIL if old_string is not unique in the file. Provide more context to make it unique.
- Use replace_all: true to replace every occurrence.
- The file_path must be an absolute path.
- You MUST read the file first before editing.
"""


class FileEditTool(Tool):
    name: str = FILE_EDIT_TOOL_NAME
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
        old_string: str = input_data["old_string"]
        new_string: str = input_data["new_string"]
        replace_all: bool = bool(input_data.get("replace_all", False))

        try:
            content = Path(abs_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return [{"type": "text", "text": f"File not found: {abs_path}"}]
        except Exception as exc:
            return [{"type": "text", "text": f"Error reading file: {exc}"}]

        count = content.count(old_string)
        if count == 0:
            return [{"type": "text", "text": f"String not found in file: {abs_path}"}]
        if count > 1 and not replace_all:
            return [{"type": "text", "text": (
                f"old_string appears {count} times in the file. "
                "Provide more surrounding context to make it unique, or use replace_all: true."
            )}]

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        try:
            Path(abs_path).write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return [{"type": "text", "text": f"Error writing file: {exc}"}]

        replaced = count if replace_all else 1
        return [{"type": "text", "text": f"Replaced {replaced} occurrence(s) in {abs_path}"}]


file_edit_tool = FileEditTool()
