"""REPLTool — execute code in an in-process REPL (Python interpreter VM)."""
from __future__ import annotations
import ast
import io
import sys
import traceback
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

REPL_TOOL_NAME = "REPL"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "Python code to execute in the REPL.",
        },
        "language": {
            "type": "string",
            "description": "Language for the REPL (currently only 'python' supported).",
            "default": "python",
        },
    },
    "required": ["code"],
}

DESCRIPTION = """\
Execute code in an in-process REPL and return the output.
Persistent session — variables defined in one call are available in subsequent calls.
Currently supports Python.
"""

# Persistent REPL namespace across calls in the same session
_repl_globals: dict[str, Any] = {"__name__": "__repl__"}


class REPLTool(Tool):
    name: str = REPL_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        from optimus.utils.permissions.permissions import has_permissions_to_use_tool
        return await has_permissions_to_use_tool(self, input_data, ctx)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        code: str = input_data["code"]
        language: str = (input_data.get("language") or "python").lower()

        if language != "python":
            return [{"type": "text", "text": f"Error: language '{language}' not supported."}]

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_buf, stderr_buf

        result_val: Any = None
        error: str | None = None
        try:
            # Try to compile as expression first to capture return value
            try:
                tree = ast.parse(code, mode="eval")
                result_val = eval(compile(tree, "<repl>", "eval"), _repl_globals)
            except SyntaxError:
                exec(compile(code, "<repl>", "exec"), _repl_globals)
        except Exception:
            error = traceback.format_exc()
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

        output_parts = []
        stdout_out = stdout_buf.getvalue()
        stderr_out = stderr_buf.getvalue()
        if stdout_out:
            output_parts.append(stdout_out)
        if stderr_out:
            output_parts.append(stderr_out)
        if error:
            output_parts.append(error)
        elif result_val is not None:
            output_parts.append(repr(result_val))

        output = "".join(output_parts) or "(no output)"
        return [{"type": "text", "text": output}]


repl_tool = REPLTool()
