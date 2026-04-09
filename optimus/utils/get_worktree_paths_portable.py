"""
Portable worktree detection — no analytics, no bootstrap deps.
Mirrors src/utils/getWorktreePathsPortable.ts

Used by session listing and anywhere that needs worktree paths without
pulling in the full CLI dependency chain.
"""
from __future__ import annotations

import asyncio
import unicodedata


async def get_worktree_paths_portable(cwd: str) -> list[str]:
    """Return all git worktree paths for the repo rooted at *cwd*.

    Runs ``git worktree list --porcelain`` and parses the output.
    Returns an empty list on any error (git not installed, not a repo, etc.).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "worktree",
            "list",
            "--porcelain",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if not stdout:
            return []
        text = stdout.decode("utf-8", errors="replace")
        return [
            unicodedata.normalize("NFC", line[len("worktree "):])
            for line in text.splitlines()
            if line.startswith("worktree ")
        ]
    except Exception:
        return []
