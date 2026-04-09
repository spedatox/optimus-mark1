"""
Branded types for session and agent IDs.
Mirrors src/types/ids.ts
"""
from __future__ import annotations

import re
from typing import NewType

# A session ID uniquely identifies a Claude Code session.
SessionId = NewType("SessionId", str)

# An agent ID uniquely identifies a subagent within a session.
AgentId = NewType("AgentId", str)

_AGENT_ID_PATTERN = re.compile(r"^a(?:.+-)?[0-9a-f]{16}$")


def as_session_id(id_: str) -> SessionId:
    """Cast a raw string to SessionId."""
    return SessionId(id_)


def as_agent_id(id_: str) -> AgentId:
    """Cast a raw string to AgentId."""
    return AgentId(id_)


def to_agent_id(s: str) -> AgentId | None:
    """Validate and brand a string as AgentId.

    Matches the format produced by create_agent_id(): `a` + optional `<label>-` + 16 hex chars.
    Returns None if the string doesn't match.
    """
    return AgentId(s) if _AGENT_ID_PATTERN.match(s) else None
