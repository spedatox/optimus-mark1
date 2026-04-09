"""
Paste store — content-addressable storage for pasted text.
Mirrors src/utils/pasteStore.ts

Files are stored as ~/.claude/paste-cache/<sha256[:16]>.txt
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from optimus.utils.debug import log_for_debugging

_PASTE_STORE_DIR = "paste-cache"


def _get_paste_store_dir() -> Path:
    from optimus.utils.env_utils import get_claude_config_home_dir
    return Path(get_claude_config_home_dir()) / _PASTE_STORE_DIR


def hash_pasted_text(content: str) -> str:
    """Return the first 16 hex characters of SHA-256(content)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _get_paste_path(hash_: str) -> Path:
    return _get_paste_store_dir() / f"{hash_}.txt"


async def store_pasted_text(hash_: str, content: str) -> None:
    """Write paste content to disk under its hash. Safe to call concurrently —
    content-addressable means same hash → same content."""
    import asyncio

    loop = asyncio.get_event_loop()

    def _write() -> None:
        try:
            d = _get_paste_store_dir()
            d.mkdir(parents=True, exist_ok=True)
            p = _get_paste_path(hash_)
            p.write_text(content, encoding="utf-8")
            # Restrict to owner
            try:
                p.chmod(0o600)
            except OSError:
                pass
            log_for_debugging(f"Stored paste {hash_} to {p}")
        except Exception as exc:
            log_for_debugging(f"Failed to store paste: {exc}")

    await loop.run_in_executor(None, _write)


async def retrieve_pasted_text(hash_: str) -> str | None:
    """Return the paste content for *hash_*, or None if not found."""
    import asyncio

    loop = asyncio.get_event_loop()

    def _read() -> str | None:
        try:
            return _get_paste_path(hash_).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except Exception as exc:
            log_for_debugging(f"Failed to retrieve paste {hash_}: {exc}")
            return None

    return await loop.run_in_executor(None, _read)


async def cleanup_old_pastes(cutoff_date: datetime) -> None:
    """Delete paste files whose mtime is older than *cutoff_date*."""
    import asyncio

    loop = asyncio.get_event_loop()

    def _cleanup() -> None:
        paste_dir = _get_paste_store_dir()
        try:
            files = list(paste_dir.iterdir())
        except OSError:
            return
        cutoff_ts = cutoff_date.timestamp()
        for f in files:
            if f.suffix != ".txt":
                continue
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    log_for_debugging(f"Cleaned up old paste: {f}")
            except OSError:
                pass

    await loop.run_in_executor(None, _cleanup)
