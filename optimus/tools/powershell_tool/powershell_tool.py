"""PowerShellTool — execute PowerShell commands (Windows/cross-platform)."""
from __future__ import annotations
import asyncio
import shutil
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

POWERSHELL_TOOL_NAME = "PowerShell"

DEFAULT_TIMEOUT_MS = 120_000
MAX_TIMEOUT_MS = 600_000
MAX_OUTPUT_BYTES = 100 * 1024  # 100 KB

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The PowerShell command to execute.",
        },
        "timeout": {
            "type": "number",
            "description": f"Timeout in ms (max {MAX_TIMEOUT_MS}). Default {DEFAULT_TIMEOUT_MS}.",
        },
        "description": {
            "type": "string",
            "description": "Short description of what the command does.",
        },
    },
    "required": ["command"],
}

DESCRIPTION = """\
Execute a PowerShell command and return its output.
Use for Windows-specific operations, file management, and system administration.
"""

_PS_EXECUTABLES = ["pwsh", "powershell"]


def _find_powershell() -> str | None:
    for name in _PS_EXECUTABLES:
        path = shutil.which(name)
        if path:
            return path
    return None


class PowerShellTool(Tool):
    name: str = POWERSHELL_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        from optimus.utils.permissions.permissions import has_permissions_to_use_tool
        return await has_permissions_to_use_tool(self, input_data, ctx)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.cwd import get_cwd

        command: str = input_data["command"]
        timeout_ms: float = float(input_data.get("timeout") or DEFAULT_TIMEOUT_MS)
        timeout_s = min(max(timeout_ms / 1000.0, 1.0), MAX_TIMEOUT_MS / 1000.0)

        ps_path = _find_powershell()
        if ps_path is None:
            return [{"type": "text", "text": "Error: PowerShell not found on this system."}]

        cwd = get_cwd()
        try:
            proc = await asyncio.create_subprocess_exec(
                ps_path, "-NonInteractive", "-Command", command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return [{"type": "text", "text": f"Error: command timed out after {timeout_s:.0f}s."}]
        except Exception as exc:
            return [{"type": "text", "text": f"Error executing PowerShell: {exc}"}]

        stdout = stdout_b[-MAX_OUTPUT_BYTES:].decode("utf-8", errors="replace")
        stderr = stderr_b[-MAX_OUTPUT_BYTES:].decode("utf-8", errors="replace")
        output = "\n".join(filter(None, [stdout, stderr]))
        if not output:
            output = f"(exit code {proc.returncode})"
        return [{"type": "text", "text": output}]


powershell_tool = PowerShellTool()
