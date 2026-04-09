"""
Pydantic schemas for permission updates.
Mirrors src/utils/permissions/PermissionUpdateSchema.ts
"""
from __future__ import annotations

from typing import Annotated, Union

from pydantic import BaseModel, Field

from optimus.types.permissions import (
    ExternalPermissionMode,
    PermissionBehavior,
    PermissionUpdateDestination,
)

# PermissionUpdate is defined as a Union of all update types in this module.
# Imported here for re-export convenience.
PermissionUpdate = None  # forward reference — resolved below after class definitions

__all__ = [
    "PermissionUpdateDestination",
    "AddRulesUpdate",
    "ReplaceRulesUpdate",
    "RemoveRulesUpdate",
    "SetModeUpdate",
    "AddDirectoriesUpdate",
    "RemoveDirectoriesUpdate",
    "PermissionUpdateModel",
    "AnyPermissionUpdate",
]

PERMISSION_UPDATE_DESTINATIONS = (
    "userSettings",
    "projectSettings",
    "localSettings",
    "session",
    "cliArg",
)


class _RuleValueModel(BaseModel):
    tool_name: str
    rule_content: str | None = None


class AddRulesUpdate(BaseModel):
    type: str = Field("addRules", pattern="addRules")
    rules: list[_RuleValueModel]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class ReplaceRulesUpdate(BaseModel):
    type: str = Field("replaceRules", pattern="replaceRules")
    rules: list[_RuleValueModel]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class RemoveRulesUpdate(BaseModel):
    type: str = Field("removeRules", pattern="removeRules")
    rules: list[_RuleValueModel]
    behavior: PermissionBehavior
    destination: PermissionUpdateDestination


class SetModeUpdate(BaseModel):
    type: str = Field("setMode", pattern="setMode")
    mode: ExternalPermissionMode
    destination: PermissionUpdateDestination


class AddDirectoriesUpdate(BaseModel):
    type: str = Field("addDirectories", pattern="addDirectories")
    directories: list[str]
    destination: PermissionUpdateDestination


class RemoveDirectoriesUpdate(BaseModel):
    type: str = Field("removeDirectories", pattern="removeDirectories")
    directories: list[str]
    destination: PermissionUpdateDestination


PermissionUpdateModel = Annotated[
    Union[
        AddRulesUpdate,
        ReplaceRulesUpdate,
        RemoveRulesUpdate,
        SetModeUpdate,
        AddDirectoriesUpdate,
        RemoveDirectoriesUpdate,
    ],
    Field(discriminator="type"),
]

# Convenience alias — the unvalidated union type used throughout the codebase
AnyPermissionUpdate = Union[
    AddRulesUpdate,
    ReplaceRulesUpdate,
    RemoveRulesUpdate,
    SetModeUpdate,
    AddDirectoriesUpdate,
    RemoveDirectoriesUpdate,
]
