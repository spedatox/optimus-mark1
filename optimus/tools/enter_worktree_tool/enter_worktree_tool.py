"""EnterWorktreeTool — create and switch to a git worktree for isolated work."""
from __future__ import annotations
import json
import re
import secrets
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

ENTER_WORKTREE_TOOL_NAME = "EnterWorktree"

_SLUG_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "Optional name for the worktree. Each '/'-separated segment may contain "
                "only letters, digits, dots, underscores, and dashes; max 64 chars total. "
                "A random name is generated if not provided."
            ),
        },
    },
    "required": [],
}

DESCRIPTION = """\
Create a new git worktree and switch the session's working directory to it.
Allows isolated work without affecting the main working tree.
"""


def _validate_slug(name: str) -> str | None:
    """Return error message if slug is invalid, else None."""
    parts = name.split("/")
    for part in parts:
        if not part:
            return "Slug segments must not be empty."
        if not _SLUG_RE.match(part):
            return f"Invalid slug segment '{part}': only letters, digits, dots, underscores, dashes allowed."
    if len(name) > 64:
        return "Worktree name must be at most 64 characters."
    return None


class EnterWorktreeTool(Tool):
    name: str = ENTER_WORKTREE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        import asyncio
        from pathlib import Path
        from optimus.utils.cwd import get_cwd, set_cwd

        name: str | None = input_data.get("name")
        if name:
            err = _validate_slug(name)
            if err:
                return [{"type": "text", "text": f"Error: {err}"}]
        else:
            name = f"optimus-{secrets.token_hex(4)}"

        cwd = get_cwd()

        # Find git root
        from optimus.utils.git import find_git_root
        git_root = find_git_root(cwd)
        if git_root is None:
            return [{"type": "text", "text": "Error: not inside a git repository."}]

        worktree_path = str(Path(git_root).parent / ".worktrees" / name)
        branch_name = f"optimus/{name}"

        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "add", "-b", branch_name, worktree_path,
            cwd=git_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return [{"type": "text", "text": f"Error creating worktree: {stderr.decode()}"}]

        set_cwd(worktree_path)
        result = {
            "worktreePath": worktree_path,
            "worktreeBranch": branch_name,
            "message": f"Switched to worktree '{name}' at {worktree_path}.",
        }
        return [{"type": "text", "text": json.dumps(result)}]


enter_worktree_tool = EnterWorktreeTool()
