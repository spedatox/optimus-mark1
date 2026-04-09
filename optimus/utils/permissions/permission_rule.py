"""
Permission rule schemas and types.
Mirrors src/utils/permissions/PermissionRule.ts
"""
from __future__ import annotations

from pydantic import BaseModel

from optimus.types.permissions import (
    PermissionBehavior,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
)

__all__ = [
    "PermissionBehavior",
    "PermissionRule",
    "PermissionRuleSource",
    "PermissionRuleValue",
    "PermissionBehaviorModel",
    "PermissionRuleValueModel",
]


class PermissionBehaviorModel(BaseModel):
    """Pydantic model for validating PermissionBehavior values."""

    behavior: PermissionBehavior


class PermissionRuleValueModel(BaseModel):
    """Pydantic model for validating PermissionRuleValue objects."""

    tool_name: str
    rule_content: str | None = None
