"""
Pattern lists for dangerous shell-tool allow-rule prefixes.
Mirrors src/utils/permissions/dangerousPatterns.ts
"""
from __future__ import annotations

import os

__all__ = [
    "CROSS_PLATFORM_CODE_EXEC",
    "DANGEROUS_BASH_PATTERNS",
]

CROSS_PLATFORM_CODE_EXEC: tuple[str, ...] = (
    # Interpreters
    "python",
    "python3",
    "python2",
    "node",
    "deno",
    "tsx",
    "ruby",
    "perl",
    "php",
    "lua",
    # Package runners
    "npx",
    "bunx",
    "npm run",
    "yarn run",
    "pnpm run",
    "bun run",
    # Shells reachable from both
    "bash",
    "sh",
    # Remote arbitrary-command wrapper
    "ssh",
)

_ANT_EXTRA: tuple[str, ...] = (
    "fa run",
    "coo",
    "gh",
    "gh api",
    "curl",
    "wget",
    "git",
    "kubectl",
    "aws",
    "gcloud",
    "gsutil",
) if os.environ.get("USER_TYPE") == "ant" else ()

DANGEROUS_BASH_PATTERNS: tuple[str, ...] = (
    *CROSS_PLATFORM_CODE_EXEC,
    "zsh",
    "fish",
    "eval",
    "exec",
    "env",
    "xargs",
    "sudo",
    *_ANT_EXTRA,
)
