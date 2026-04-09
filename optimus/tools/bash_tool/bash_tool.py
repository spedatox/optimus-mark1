"""
BashTool — execute shell commands.
Mirrors src/tools/BashTool/BashTool.tsx (execution logic; React UI omitted).
"""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from optimus.tool import Tool, ToolUseContext, ValidationResult

BASH_TOOL_NAME = "Bash"

# Defaults match the TS source (getDefaultBashTimeoutMs / getMaxBashTimeoutMs)
DEFAULT_TIMEOUT_MS = 120_000
MAX_TIMEOUT_MS = 600_000

# Commands the model should prefer dedicated tools for
_AVOID_COMMANDS = {"find", "grep", "cat", "head", "tail", "sed", "awk", "echo"}

DESCRIPTION = """\
Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not. \
The shell environment is initialized from the user's profile (bash or zsh).

IMPORTANT: Avoid using this tool to run `find`, `grep`, `cat`, `head`, `tail`, \
`sed`, `awk`, or `echo` commands unless a dedicated tool cannot accomplish your task.

# Instructions
- If your command will create new directories or files, first run `ls` to verify \
the parent directory exists.
- Always quote file paths that contain spaces with double quotes.
- Try to maintain your current working directory by using absolute paths.
- You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). \
By default, your command will timeout after 120000ms (2 minutes).
- When issuing multiple commands, use `&&` to chain sequential commands and \
make multiple tool calls for independent parallel commands.
- For git commands: never skip hooks (--no-verify) unless the user explicitly asks. \
Prefer creating new commits over amending.
"""


class BashInput(BaseModel):
    command: str = Field(..., description="The bash command to execute.")
    timeout: int | None = Field(
        None,
        description=(
            f"Optional timeout in milliseconds (max {MAX_TIMEOUT_MS}). "
            f"Defaults to {DEFAULT_TIMEOUT_MS}."
        ),
    )
    description: str | None = Field(
        None,
        description="Clear, concise description of what this command does.",
    )
    run_in_background: bool | None = Field(
        None,
        description=(
            "Set to true to run this command in the background. "
            "Only use this if you don't need the result immediately."
        ),
    )


INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The bash command to execute.",
        },
        "timeout": {
            "type": "integer",
            "description": (
                f"Optional timeout in milliseconds (max {MAX_TIMEOUT_MS}). "
                f"Defaults to {DEFAULT_TIMEOUT_MS}."
            ),
        },
        "description": {
            "type": "string",
            "description": "Clear, concise description of what this command does.",
        },
        "run_in_background": {
            "type": "boolean",
            "description": (
                "Set to true to run this command in the background. "
                "Only use this if you don't need the result immediately and are "
                "OK being notified when the command completes later."
            ),
        },
    },
    "required": ["command"],
}


class BashTool(Tool):
    name: str = BASH_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(
        self, input_data: dict[str, Any], ctx: ToolUseContext
    ) -> ValidationResult:
        from optimus.utils.permissions.permissions import has_permissions_to_use_tool
        command = input_data.get("command", "")
        result = await has_permissions_to_use_tool(
            self.name, {"command": command}, ctx
        )
        if result.behavior == "allow":
            return ValidationResult(allowed=True)
        if result.behavior == "deny":
            return ValidationResult(allowed=False, message=result.message or "")
        # "ask" — surface to user (caller handles this)
        return ValidationResult(allowed=False, message=result.message or "", needs_prompt=True)

    async def call(
        self, input_data: dict[str, Any], ctx: ToolUseContext
    ) -> list[dict[str, Any]]:
        from optimus.utils.shell.bash_provider import create_bash_provider, DEFAULT_TIMEOUT_S
        from optimus.utils.cwd import get_cwd

        command: str = input_data["command"]
        timeout_ms: int = input_data.get("timeout") or DEFAULT_TIMEOUT_MS
        timeout_ms = min(timeout_ms, MAX_TIMEOUT_MS)
        timeout_s = timeout_ms / 1000.0

        provider = create_bash_provider()
        result = await provider.exec(
            command,
            cwd=get_cwd(),
            timeout=timeout_s,
        )

        # Update CWD if changed
        if result.new_cwd and os.path.isdir(result.new_cwd):
            try:
                from optimus.bootstrap.state import set_cwd_state
                set_cwd_state(result.new_cwd)
            except Exception:
                pass

        # Build output text
        output_parts: list[str] = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(result.stderr)
        if result.interrupted:
            output_parts.append("\n[Process timed out]")

        output = "\n".join(output_parts).rstrip()

        if result.exit_code != 0 and not result.interrupted:
            output += f"\nExit code: {result.exit_code}"

        return [{"type": "text", "text": output or "(no output)"}]


# Singleton instance for registry
bash_tool = BashTool()
