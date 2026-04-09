"""
Permission result helpers.
Mirrors src/utils/permissions/PermissionResult.ts
"""
from __future__ import annotations

from optimus.types.permissions import (
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionDecision,
    PermissionDecisionReason,
    PermissionDenyDecision,
    PermissionMetadata,
    PermissionResult,
)

__all__ = [
    "PermissionAllowDecision",
    "PermissionAskDecision",
    "PermissionDecision",
    "PermissionDecisionReason",
    "PermissionDenyDecision",
    "PermissionMetadata",
    "PermissionResult",
    "get_rule_behavior_description",
]


def get_rule_behavior_description(behavior: str) -> str:
    """Returns a prose description for a permission result behavior."""
    if behavior == "allow":
        return "allowed"
    if behavior == "deny":
        return "denied"
    return "asked for confirmation for"
