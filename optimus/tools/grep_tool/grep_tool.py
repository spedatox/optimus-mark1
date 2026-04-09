"""GrepTool — content search using ripgrep or Python regex. Mirrors src/tools/GrepTool/GrepTool.ts"""
from __future__ import annotations
import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

GREP_TOOL_NAME = "Grep"
MAX_RESULTS = 1000

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "The regular expression pattern to search for."},
        "path": {"type": "string", "description": "File or directory to search in. Defaults to current directory."},
        "include": {"type": "string", "description": "Glob pattern to filter files (e.g. '*.py', '*.{ts,tsx}')."},
        "-i": {"type": "boolean", "description": "Case insensitive search."},
        "output_mode": {
            "type": "string",
            "enum": ["content", "files_with_matches", "count"],
            "description": "Output mode. 'content' shows matching lines, 'files_with_matches' shows file paths, 'count' shows match counts.",
        },
        "context": {"type": "integer", "description": "Lines of context around each match."},
        "head_limit": {"type": "integer", "description": "Limit output to first N lines."},
    },
    "required": ["pattern"],
}

DESCRIPTION = """\
A powerful search tool built on ripgrep (falls back to Python re).

Usage:
- Supports full regex syntax.
- Filter files with include parameter (e.g., \"*.py\").
- output_mode: \"content\" shows matching lines, \"files_with_matches\" shows only file paths, \"count\" shows match counts.
- Use the Agent tool for open-ended searches requiring multiple rounds.
"""


class GrepTool(Tool):
    name: str = GREP_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.path import expand_path
        from optimus.utils.cwd import get_cwd

        pattern: str = input_data["pattern"]
        base = expand_path(input_data.get("path") or get_cwd(), get_cwd())
        include: str | None = input_data.get("include")
        case_insensitive: bool = bool(input_data.get("-i", False))
        output_mode: str = input_data.get("output_mode", "files_with_matches")
        context_lines: int = int(input_data.get("context", 0))
        head_limit: int = int(input_data.get("head_limit", 250))

        rg = shutil.which("rg")
        if rg:
            output = await _rg_search(
                rg, pattern, base, include, case_insensitive, output_mode, context_lines, head_limit
            )
        else:
            output = _python_search(
                pattern, base, include, case_insensitive, output_mode, context_lines, head_limit
            )

        return [{"type": "text", "text": output or "No matches found."}]


async def _rg_search(
    rg: str, pattern: str, path: str, include: str | None,
    case_insensitive: bool, output_mode: str, context: int, limit: int
) -> str:
    args = [rg, "--no-heading"]
    if case_insensitive:
        args.append("-i")
    if include:
        args += ["--glob", include]
    if output_mode == "files_with_matches":
        args.append("-l")
    elif output_mode == "count":
        args.append("-c")
    elif context > 0:
        args += ["-C", str(context)]
    args += [pattern, path]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        if limit:
            lines = lines[:limit]
        return "\n".join(lines)
    except Exception:
        return ""


def _python_search(
    pattern: str, path: str, include: str | None,
    case_insensitive: bool, output_mode: str, context: int, limit: int
) -> str:
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return f"Invalid regex: {exc}"

    import fnmatch
    results: list[str] = []
    count_map: dict[str, int] = {}

    for root, _, files in os.walk(path):
        for fname in files:
            if include and not fnmatch.fnmatch(fname, include):
                continue
            fpath = os.path.join(root, fname)
            try:
                text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lines = text.splitlines()
            file_matches: list[str] = []
            for i, line in enumerate(lines):
                if rx.search(line):
                    if output_mode == "content":
                        file_matches.append(f"{fpath}:{i+1}:{line}")
                    elif output_mode == "files_with_matches":
                        file_matches.append(fpath)
                        break
                    elif output_mode == "count":
                        count_map[fpath] = count_map.get(fpath, 0) + 1
            results.extend(file_matches)
            if len(results) >= limit:
                break

    if output_mode == "count":
        results = [f"{k}:{v}" for k, v in count_map.items()]

    return "\n".join(results[:limit])


grep_tool = GrepTool()
