"""
Prompt history — read/write ~/.claude/history.jsonl.
Mirrors src/history.ts

Stores user prompts (with pasted content) so they can be browsed via
Up-arrow and Ctrl+R. Writes are buffered in memory and flushed to disk
asynchronously under an advisory file lock.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HISTORY_ITEMS = 100
MAX_PASTED_CONTENT_LENGTH = 1024


# ---------------------------------------------------------------------------
# Reference formatting / parsing
# ---------------------------------------------------------------------------

def get_pasted_text_ref_num_lines(text: str) -> int:
    """Count newline sequences in text (preserves TypeScript behavior)."""
    return len(re.findall(r"\r\n|\r|\n", text))


def format_pasted_text_ref(id_: int, num_lines: int) -> str:
    if num_lines == 0:
        return f"[Pasted text #{id_}]"
    return f"[Pasted text #{id_} +{num_lines} lines]"


def format_image_ref(id_: int) -> str:
    return f"[Image #{id_}]"


_REF_PATTERN = re.compile(
    r"\[(Pasted text|Image|\.\.\.Truncated text) #(\d+)(?: \+\d+ lines)?(\.)*\]"
)


def parse_references(input_: str) -> list[dict[str, Any]]:
    matches = []
    for m in _REF_PATTERN.finditer(input_):
        id_ = int(m.group(2) or "0")
        if id_ > 0:
            matches.append({"id": id_, "match": m.group(0), "index": m.start()})
    return matches


def expand_pasted_text_refs(
    input_: str, pasted_contents: dict[int, dict[str, Any]]
) -> str:
    """Replace [Pasted text #N] placeholders with their actual content."""
    refs = parse_references(input_)
    expanded = input_
    for ref in reversed(refs):
        content = pasted_contents.get(ref["id"])
        if not content or content.get("type") != "text":
            continue
        text = content.get("content", "")
        idx = ref["index"]
        mlen = len(ref["match"])
        expanded = expanded[:idx] + text + expanded[idx + mlen:]
    return expanded


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

def _get_history_path() -> str:
    from optimus.utils.env_utils import get_claude_config_home_dir
    return str(Path(get_claude_config_home_dir()) / "history.jsonl")


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_pending_entries: list[dict[str, Any]] = []
_is_writing = False
_current_flush_task: asyncio.Task | None = None
_cleanup_registered = False
_last_added_entry: dict[str, Any] | None = None
_skipped_timestamps: set[int] = set()

_write_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# File lock (cross-platform advisory)
# ---------------------------------------------------------------------------

def _acquire_lock_sync(lock_path: str) -> Any:
    """Acquire an exclusive advisory file lock synchronously."""
    lock_file = open(lock_path, "w")
    try:
        import sys
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX)
    except Exception:
        lock_file.close()
        raise
    return lock_file


def _release_lock_sync(lock_file: Any) -> None:
    try:
        import sys
        if sys.platform == "win32":
            import msvcrt
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    finally:
        lock_file.close()


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------

async def _immediate_flush_history() -> None:
    global _pending_entries

    if not _pending_entries:
        return

    history_path = _get_history_path()
    lock_path = f"{history_path}.lock"
    loop = asyncio.get_event_loop()

    def _flush_sync(entries: list[dict[str, Any]]) -> None:
        Path(history_path).parent.mkdir(parents=True, exist_ok=True)
        # Ensure file exists (append mode creates if missing, with secure perms)
        if not Path(history_path).exists():
            Path(history_path).touch(mode=0o600)

        lock_file = None
        try:
            lock_file = _acquire_lock_sync(lock_path)
            lines = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(lines)
        except Exception as exc:
            # Log and swallow — history write failures are non-fatal
            try:
                from optimus.utils.debug import log_for_debugging
                log_for_debugging(f"Failed to write prompt history: {exc}")
            except Exception:
                pass
        finally:
            if lock_file is not None:
                _release_lock_sync(lock_file)
            try:
                os.unlink(lock_path)
            except OSError:
                pass

    entries_to_write = list(_pending_entries)
    _pending_entries = []
    await loop.run_in_executor(None, _flush_sync, entries_to_write)


async def _flush_prompt_history(retries: int = 0) -> None:
    global _is_writing

    if _is_writing or not _pending_entries:
        return
    if retries > 5:
        return

    _is_writing = True
    try:
        await _immediate_flush_history()
    finally:
        _is_writing = False
        if _pending_entries:
            await asyncio.sleep(0.5)
            asyncio.ensure_future(_flush_prompt_history(retries + 1))


# ---------------------------------------------------------------------------
# Reverse line reader
# ---------------------------------------------------------------------------

async def _read_lines_reverse(file_path: str) -> AsyncGenerator[str, None]:
    """Yield lines from a file in reverse order."""
    loop = asyncio.get_event_loop()

    def _read_all() -> list[str]:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()

    try:
        lines = await loop.run_in_executor(None, _read_all)
    except FileNotFoundError:
        return

    for line in reversed(lines):
        if line.strip():
            yield line


# ---------------------------------------------------------------------------
# Log entry reader
# ---------------------------------------------------------------------------

async def _make_log_entry_reader() -> AsyncGenerator[dict[str, Any], None]:
    from optimus.bootstrap.state import get_session_id

    current_session = get_session_id()

    # Pending (not yet flushed) entries — newest first
    for entry in reversed(_pending_entries):
        yield entry

    history_path = _get_history_path()
    try:
        async for line in _read_lines_reverse(history_path):
            try:
                entry = json.loads(line)
                if (
                    entry.get("sessionId") == current_session
                    and entry.get("timestamp") in _skipped_timestamps
                ):
                    continue
                yield entry
            except Exception:
                pass
    except FileNotFoundError:
        return


# ---------------------------------------------------------------------------
# Pasted content resolution
# ---------------------------------------------------------------------------

async def _resolve_stored_pasted_content(
    stored: dict[str, Any],
) -> dict[str, Any] | None:
    if stored.get("content"):
        return {
            "id": stored["id"],
            "type": stored["type"],
            "content": stored["content"],
            "mediaType": stored.get("mediaType"),
            "filename": stored.get("filename"),
        }
    if stored.get("contentHash"):
        try:
            from optimus.utils.paste_store import retrieve_pasted_text
            content = await retrieve_pasted_text(stored["contentHash"])
            if content:
                return {
                    "id": stored["id"],
                    "type": stored["type"],
                    "content": content,
                    "mediaType": stored.get("mediaType"),
                    "filename": stored.get("filename"),
                }
        except Exception:
            pass
    return None


async def _log_entry_to_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    pasted_contents: dict[int, Any] = {}
    for id_str, stored in (entry.get("pastedContents") or {}).items():
        resolved = await _resolve_stored_pasted_content(stored)
        if resolved:
            pasted_contents[int(id_str)] = resolved
    return {"display": entry.get("display", ""), "pastedContents": pasted_contents}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def make_history_reader() -> AsyncGenerator[dict[str, Any], None]:
    async for entry in _make_log_entry_reader():
        yield await _log_entry_to_history_entry(entry)


async def get_history() -> AsyncGenerator[dict[str, Any], None]:
    """
    Get history entries for the current project, current session first.
    Mirrors getHistory() in history.ts.
    """
    from optimus.bootstrap.state import get_project_root, get_session_id

    current_project = get_project_root()
    current_session = get_session_id()
    other_entries: list[dict[str, Any]] = []
    yielded = 0

    async for entry in _make_log_entry_reader():
        if not entry or not isinstance(entry.get("project"), str):
            continue
        if entry["project"] != current_project:
            continue

        if entry.get("sessionId") == current_session:
            yield await _log_entry_to_history_entry(entry)
            yielded += 1
        else:
            other_entries.append(entry)

        if yielded + len(other_entries) >= MAX_HISTORY_ITEMS:
            break

    for entry in other_entries:
        if yielded >= MAX_HISTORY_ITEMS:
            return
        yield await _log_entry_to_history_entry(entry)
        yielded += 1


async def get_timestamped_history() -> AsyncGenerator[dict[str, Any], None]:
    """Ctrl+R history picker — deduped by display text, newest first."""
    from optimus.bootstrap.state import get_project_root

    current_project = get_project_root()
    seen: set[str] = set()

    async for entry in _make_log_entry_reader():
        if not entry or not isinstance(entry.get("project"), str):
            continue
        if entry["project"] != current_project:
            continue
        display = entry.get("display", "")
        if display in seen:
            continue
        seen.add(display)

        yield {
            "display": display,
            "timestamp": entry.get("timestamp", 0),
            "resolve": lambda e=entry: _log_entry_to_history_entry(e),
        }

        if len(seen) >= MAX_HISTORY_ITEMS:
            return


def add_to_history(command: dict[str, Any] | str) -> None:
    """
    Add a prompt to history. Non-blocking — flushes to disk asynchronously.
    Mirrors addToHistory() in history.ts.
    """
    global _cleanup_registered, _current_flush_task, _last_added_entry

    # Skip when running in a tmux session spawned by Claude Code
    from optimus.utils.env_utils import is_env_truthy
    if is_env_truthy(os.environ.get("CLAUDE_CODE_SKIP_PROMPT_HISTORY")):
        return

    asyncio.ensure_future(_add_to_prompt_history(command))


async def _add_to_prompt_history(command: dict[str, Any] | str) -> None:
    global _last_added_entry, _current_flush_task

    from optimus.bootstrap.state import get_project_root, get_session_id

    if isinstance(command, str):
        entry_base = {"display": command, "pastedContents": {}}
    else:
        entry_base = dict(command)

    stored_pasted: dict[str, Any] = {}
    for id_, content in (entry_base.get("pastedContents") or {}).items():
        if isinstance(content, dict) and content.get("type") == "image":
            continue
        text = content.get("content", "") if isinstance(content, dict) else ""
        if len(text) <= MAX_PASTED_CONTENT_LENGTH:
            stored_pasted[str(id_)] = {
                "id": content.get("id", id_),
                "type": content.get("type", "text"),
                "content": text,
                "mediaType": content.get("mediaType"),
                "filename": content.get("filename"),
            }
        else:
            try:
                from optimus.utils.paste_store import hash_pasted_text, store_pasted_text
                h = hash_pasted_text(text)
                stored_pasted[str(id_)] = {
                    "id": content.get("id", id_),
                    "type": content.get("type", "text"),
                    "contentHash": h,
                    "mediaType": content.get("mediaType"),
                    "filename": content.get("filename"),
                }
                asyncio.ensure_future(store_pasted_text(h, text))
            except Exception:
                stored_pasted[str(id_)] = {
                    "id": content.get("id", id_),
                    "type": content.get("type", "text"),
                    "content": text[:MAX_PASTED_CONTENT_LENGTH],
                }

    log_entry: dict[str, Any] = {
        "display": entry_base.get("display", ""),
        "pastedContents": stored_pasted,
        "timestamp": int(time.time() * 1000),
        "project": get_project_root(),
        "sessionId": get_session_id(),
    }

    _pending_entries.append(log_entry)
    _last_added_entry = log_entry
    _current_flush_task = asyncio.ensure_future(_flush_prompt_history(0))


def clear_pending_history_entries() -> None:
    global _last_added_entry
    _pending_entries.clear()
    _last_added_entry = None
    _skipped_timestamps.clear()


def remove_last_from_history() -> None:
    """Undo the most recent add_to_history call."""
    global _last_added_entry

    if not _last_added_entry:
        return

    entry = _last_added_entry
    _last_added_entry = None

    # Fast path: still in the pending buffer
    try:
        idx = len(_pending_entries) - 1 - _pending_entries[::-1].index(entry)
        _pending_entries.pop(idx)
    except ValueError:
        # Already flushed — add to skip set
        ts = entry.get("timestamp")
        if ts is not None:
            _skipped_timestamps.add(ts)
