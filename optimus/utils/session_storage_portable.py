"""
Portable session storage utilities — pure Python, no internal deps on logging/flags.
Mirrors src/utils/sessionStoragePortable.ts

Shared between the CLI session storage and any SDK consumers.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LITE_READ_BUF_SIZE = 65536
MAX_SANITIZED_LENGTH = 200
SKIP_PRECOMPACT_THRESHOLD = 5 * 1024 * 1024  # 5 MB

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_SKIP_FIRST_PROMPT_PATTERN = re.compile(
    r"^(?:\s*<[a-z][\w-]*[\s>]|\[Request interrupted by user[^\]]*\])"
)
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>")
_BASH_INPUT_RE = re.compile(r"<bash-input>([\s\S]*?)</bash-input>")

# ---------------------------------------------------------------------------
# UUID validation
# ---------------------------------------------------------------------------


def validate_uuid(maybe_uuid: object) -> str | None:
    if not isinstance(maybe_uuid, str):
        return None
    return maybe_uuid if _UUID_RE.match(maybe_uuid) else None


# ---------------------------------------------------------------------------
# JSON string field extraction (no full parse — works on truncated lines)
# ---------------------------------------------------------------------------


def unescape_json_string(raw: str) -> str:
    if "\\" not in raw:
        return raw
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw


def extract_json_string_field(text: str, key: str) -> str | None:
    for pattern in (f'"{key}":"', f'"{key}": "'):
        idx = text.find(pattern)
        if idx < 0:
            continue
        value_start = idx + len(pattern)
        i = value_start
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                return unescape_json_string(text[value_start:i])
            i += 1
    return None


def extract_last_json_string_field(text: str, key: str) -> str | None:
    last_value: str | None = None
    for pattern in (f'"{key}":"', f'"{key}": "'):
        search_from = 0
        while True:
            idx = text.find(pattern, search_from)
            if idx < 0:
                break
            value_start = idx + len(pattern)
            i = value_start
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    last_value = unescape_json_string(text[value_start:i])
                    break
                i += 1
            search_from = i + 1
    return last_value


# ---------------------------------------------------------------------------
# First prompt extraction
# ---------------------------------------------------------------------------


def extract_first_prompt_from_head(head: str) -> str:
    command_fallback = ""
    for line in head.splitlines():
        if '"type":"user"' not in line and '"type": "user"' not in line:
            continue
        if '"tool_result"' in line:
            continue
        if '"isMeta":true' in line or '"isMeta": true' in line:
            continue
        if '"isCompactSummary":true' in line or '"isCompactSummary": true' in line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("type") != "user":
                continue
            message = entry.get("message")
            if not message:
                continue
            content = message.get("content")
            texts: list[str] = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        t = block.get("text")
                        if isinstance(t, str):
                            texts.append(t)
            for raw in texts:
                result = raw.replace("\n", " ").strip()
                if not result:
                    continue
                cmd_match = _COMMAND_NAME_RE.search(result)
                if cmd_match:
                    if not command_fallback:
                        command_fallback = cmd_match.group(1)
                    continue
                bash_match = _BASH_INPUT_RE.search(result)
                if bash_match:
                    return f"! {bash_match.group(1).strip()}"
                if _SKIP_FIRST_PROMPT_PATTERN.match(result):
                    continue
                if len(result) > 200:
                    result = result[:200].rstrip() + "\u2026"
                return result
        except Exception:
            continue
    return command_fallback


# ---------------------------------------------------------------------------
# File I/O — head and tail reads
# ---------------------------------------------------------------------------


class LiteSessionFile(NamedTuple):
    mtime: float
    size: int
    head: str
    tail: str


async def read_head_and_tail(
    file_path: str, file_size: int
) -> tuple[str, str]:
    """Read the first and last LITE_READ_BUF_SIZE bytes of a file."""
    try:
        loop = asyncio.get_event_loop()

        def _read() -> tuple[str, str]:
            with open(file_path, "rb") as f:
                head_bytes = f.read(LITE_READ_BUF_SIZE)
                if not head_bytes:
                    return "", ""
                head = head_bytes.decode("utf-8", errors="replace")
                tail_offset = max(0, file_size - LITE_READ_BUF_SIZE)
                if tail_offset > 0:
                    f.seek(tail_offset)
                    tail_bytes = f.read(LITE_READ_BUF_SIZE)
                    tail = tail_bytes.decode("utf-8", errors="replace")
                else:
                    tail = head
                return head, tail

        return await loop.run_in_executor(None, _read)
    except Exception:
        return "", ""


async def read_session_lite(file_path: str) -> LiteSessionFile | None:
    """Open a session file, stat it, and read head + tail."""
    try:
        loop = asyncio.get_event_loop()

        def _read() -> LiteSessionFile | None:
            try:
                stat = os.stat(file_path)
                with open(file_path, "rb") as f:
                    head_bytes = f.read(LITE_READ_BUF_SIZE)
                    if not head_bytes:
                        return None
                    head = head_bytes.decode("utf-8", errors="replace")
                    tail_offset = max(0, stat.st_size - LITE_READ_BUF_SIZE)
                    if tail_offset > 0:
                        f.seek(tail_offset)
                        tail_bytes = f.read(LITE_READ_BUF_SIZE)
                        tail = tail_bytes.decode("utf-8", errors="replace")
                    else:
                        tail = head
                    return LiteSessionFile(
                        mtime=stat.st_mtime * 1000,
                        size=stat.st_size,
                        head=head,
                        tail=tail,
                    )
            except Exception:
                return None

        return await loop.run_in_executor(None, _read)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Path sanitization
# ---------------------------------------------------------------------------


def _djb2_hash(s: str) -> int:
    h = 5381
    for c in s.encode("utf-8"):
        h = ((h << 5) + h + c) & 0xFFFFFFFF
    return h


def sanitize_path(name: str) -> str:
    """
    Make a string safe for use as a directory/file name.
    Replaces non-alphanumeric chars with hyphens.
    Truncates long names and appends a hash for uniqueness.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9]", "-", name)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return sanitized
    h = abs(_djb2_hash(name))
    hash_str = _to_base36(h)
    return f"{sanitized[:MAX_SANITIZED_LENGTH]}-{hash_str}"


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []
    while n:
        result.append(digits[n % 36])
        n //= 36
    return "".join(reversed(result))


# ---------------------------------------------------------------------------
# Project directory helpers
# ---------------------------------------------------------------------------


def get_projects_dir() -> str:
    from optimus.utils.env_utils import get_claude_config_home_dir
    return str(Path(get_claude_config_home_dir()) / "projects")


def get_project_dir(project_dir: str) -> str:
    return str(Path(get_projects_dir()) / sanitize_path(project_dir))


async def canonicalize_path(dir_: str) -> str:
    """Resolve a directory to its canonical realpath with error fallback."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, lambda: str(Path(dir_).resolve()))
    except Exception:
        return dir_


async def find_project_dir(project_path: str) -> str | None:
    """
    Find project dir tolerating hash mismatches for long paths.
    The CLI uses Bun.hash while Python uses djb2 — for paths exceeding
    MAX_SANITIZED_LENGTH these produce different suffixes, so we fall back
    to prefix-based scanning.
    """
    loop = asyncio.get_event_loop()
    exact = get_project_dir(project_path)
    try:
        await loop.run_in_executor(None, lambda: os.listdir(exact))
        return exact
    except OSError:
        pass

    sanitized = sanitize_path(project_path)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return None

    prefix = sanitized[:MAX_SANITIZED_LENGTH]
    projects_dir = get_projects_dir()
    try:
        entries = await loop.run_in_executor(None, lambda: os.listdir(projects_dir))
        for entry in entries:
            full = str(Path(projects_dir) / entry)
            if entry.startswith(prefix + "-") and Path(full).is_dir():
                return full
    except OSError:
        pass
    return None


class _ResolvedSession(NamedTuple):
    file_path: str
    project_path: str | None
    file_size: int


async def resolve_session_file_path(
    session_id: str, dir_: str | None = None
) -> _ResolvedSession | None:
    """
    Resolve a sessionId to its on-disk JSONL file path.
    When dir_ is provided: look in that project dir (with worktree fallback).
    When dir_ is None: scan all project directories.
    """
    loop = asyncio.get_event_loop()
    file_name = f"{session_id}.jsonl"

    async def _check(file_path: str) -> int | None:
        try:
            s = await loop.run_in_executor(None, lambda: os.stat(file_path))
            return s.st_size if s.st_size > 0 else None
        except OSError:
            return None

    if dir_:
        canonical = await canonicalize_path(dir_)
        project_dir = await find_project_dir(canonical)
        if project_dir:
            fp = str(Path(project_dir) / file_name)
            size = await _check(fp)
            if size is not None:
                return _ResolvedSession(fp, canonical, size)

        # Worktree fallback
        try:
            from optimus.utils.get_worktree_paths_portable import get_worktree_paths_portable
            worktree_paths = await get_worktree_paths_portable(canonical)
        except Exception:
            worktree_paths = []

        for wt in worktree_paths:
            if wt == canonical:
                continue
            wt_project_dir = await find_project_dir(wt)
            if not wt_project_dir:
                continue
            fp = str(Path(wt_project_dir) / file_name)
            size = await _check(fp)
            if size is not None:
                return _ResolvedSession(fp, wt, size)
        return None

    # No dir — scan all project directories
    projects_dir = get_projects_dir()
    try:
        entries = await loop.run_in_executor(None, lambda: os.listdir(projects_dir))
    except OSError:
        return None

    for name in entries:
        fp = str(Path(projects_dir) / name / file_name)
        size = await _check(fp)
        if size is not None:
            return _ResolvedSession(fp, None, size)
    return None


# ---------------------------------------------------------------------------
# Transcript chunked reader (compact-boundary aware)
# ---------------------------------------------------------------------------

_COMPACT_BOUNDARY_MARKER = b'"compact_boundary"'
_ATTR_SNAP_PREFIX = b'{"type":"attribution-snapshot"'
_SYSTEM_PREFIX = b'{"type":"system"'
TRANSCRIPT_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB


class _TranscriptResult(NamedTuple):
    boundary_start_offset: int
    post_boundary_buf: bytes
    has_preserved_segment: bool


def _parse_boundary_line(line: str) -> dict | None:
    try:
        parsed = json.loads(line)
        if parsed.get("type") != "system" or parsed.get("subtype") != "compact_boundary":
            return None
        has_preserved = bool(
            (parsed.get("compactMetadata") or {}).get("preservedSegment")
        )
        return {"has_preserved_segment": has_preserved}
    except Exception:
        return None


async def read_transcript_for_load(
    file_path: str, file_size: int
) -> _TranscriptResult:
    """
    Single forward chunked read stripping attr-snaps and truncating on
    compact boundaries. Mirrors readTranscriptForLoad in sessionStoragePortable.ts.
    """
    loop = asyncio.get_event_loop()

    def _read_sync() -> _TranscriptResult:
        out = bytearray()
        boundary_start_offset = 0
        has_preserved_segment = False
        last_snap: bytes | None = None
        carry = bytearray()

        with open(file_path, "rb") as f:
            file_pos = 0
            while file_pos < file_size:
                to_read = min(TRANSCRIPT_READ_CHUNK_SIZE, file_size - file_pos)
                chunk = f.read(to_read)
                if not chunk:
                    break
                file_pos += len(chunk)

                # Combine carry + chunk
                buf = bytes(carry) + chunk
                carry.clear()

                lines = buf.split(b"\n")
                # Last element may be incomplete — save as carry
                if not buf.endswith(b"\n"):
                    carry.extend(lines.pop())

                for line_bytes in lines:
                    line_with_nl = line_bytes + b"\n"
                    if line_bytes.startswith(_ATTR_SNAP_PREFIX):
                        last_snap = bytes(line_with_nl)
                        continue
                    if _COMPACT_BOUNDARY_MARKER in line_bytes and line_bytes.startswith(_SYSTEM_PREFIX):
                        result = _parse_boundary_line(line_bytes.decode("utf-8", errors="replace"))
                        if result:
                            if result["has_preserved_segment"]:
                                has_preserved_segment = True
                            else:
                                boundary_start_offset = file_pos - len(chunk) + buf.find(line_with_nl)
                                out.clear()
                                has_preserved_segment = False
                                last_snap = None
                            continue
                    out.extend(line_with_nl)

        # Handle leftover carry
        if carry:
            if bytes(carry).startswith(_ATTR_SNAP_PREFIX):
                last_snap = bytes(carry)
            else:
                out.extend(carry)

        # Append last attr-snap at end
        if last_snap:
            if out and out[-1] != ord(b"\n"):
                out.extend(b"\n")
            out.extend(last_snap)

        return _TranscriptResult(
            boundary_start_offset=boundary_start_offset,
            post_boundary_buf=bytes(out),
            has_preserved_segment=has_preserved_segment,
        )

    return await loop.run_in_executor(None, _read_sync)
