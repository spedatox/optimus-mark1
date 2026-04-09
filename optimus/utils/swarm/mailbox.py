"""Teammate mailbox — async message passing between swarm agents."""
from __future__ import annotations
import asyncio
import json
from typing import Any

_mailboxes: dict[str, asyncio.Queue] = {}


def _get_mailbox(agent_id: str) -> asyncio.Queue:
    if agent_id not in _mailboxes:
        _mailboxes[agent_id] = asyncio.Queue()
    return _mailboxes[agent_id]


async def write_to_mailbox(agent_id: str, message: dict[str, Any]) -> None:
    await _get_mailbox(agent_id).put(message)


async def read_from_mailbox(agent_id: str, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        return await asyncio.wait_for(_get_mailbox(agent_id).get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
