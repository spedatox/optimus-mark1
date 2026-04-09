"""ExitWorktreeTool — exit the current git worktree and return to main tree."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

EXIT_WORKTREE_TOOL_NAME = "ExitWorktree"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["keep", "remove"],
            "description": '"keep" leaves the worktree on disk; "remove" deletes it.',
        },
        "discard_changes": {
            "type": "boolean",
            "description": (
                "Required true when action is 'remove' and the worktree has "
                "uncommitted files or unmerged commits."
            ),
        },
    },
    "required": ["action"],
}

DESCRIPTION = """\
Exit the current git worktree and return to the original working directory.
Use action='keep' to preserve the worktree, 'remove' to delete it.
"""


class ExitWorktreeTool(Tool):
    name: str = EXIT_WORKTREE_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        import asyncio
        from optimus.utils.cwd import get_cwd, set_cwd
        from optimus.utils.git import find_canonical_git_root

        action: str = input_data["action"]
        discard: bool = bool(input_data.get("discard_changes", False))

        current_wt = get_cwd()
        canonical_root = find_canonical_git_root(current_wt)
        if canonical_root is None:
            return [{"type": "text", "text": "Error: not inside a git repository."}]

        if action == "remove":
            if not discard:
                # Check for uncommitted changes
                proc = await asyncio.create_subprocess_exec(
                    "git", "status", "--porcelain",
                    cwd=current_wt,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if stdout.strip():
                    return [{"type": "text", "text": (
                        "Error: worktree has uncommitted changes. "
                        "Set discard_changes=true to force removal."
                    )}]

            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "remove", "--force" if discard else "", current_wt,
                cwd=canonical_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return [{"type": "text", "text": f"Error removing worktree: {stderr.decode()}"}]

        set_cwd(canonical_root)
        result = {
            "action": action,
            "originalCwd": canonical_root,
            "message": f"Exited worktree. CWD is now {canonical_root}.",
        }
        return [{"type": "text", "text": json.dumps(result)}]


exit_worktree_tool = ExitWorktreeTool()
