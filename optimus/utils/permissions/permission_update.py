"""
Permission update application and persistence.
Mirrors src/utils/permissions/PermissionUpdate.ts
"""
from __future__ import annotations

import copy
from typing import Any

from optimus.types.permissions import (
    AdditionalWorkingDirectory,
    PermissionRuleValue,
    PermissionUpdateDestination,
    ToolPermissionContext,
    WorkingDirectorySource,
)

# PermissionUpdate is a plain dict or Pydantic model throughout the codebase.
PermissionUpdate = Any  # type alias for unannotated update dicts

__all__ = [
    "extract_rules",
    "has_rules",
    "apply_permission_update",
    "apply_permission_updates",
    "supports_persistence",
    "persist_permission_update",
    "persist_permission_updates",
    "create_read_rule_suggestion",
]

_EDITABLE_SOURCES = ("localSettings", "userSettings", "projectSettings")


def extract_rules(updates: list[PermissionUpdate] | None) -> list[PermissionRuleValue]:
    """Extracts rule values from addRules-type updates."""
    if not updates:
        return []
    result: list[PermissionRuleValue] = []
    for update in updates:
        if isinstance(update, dict) and update.get("type") == "addRules":
            result.extend(update.get("rules", []))
    return result


def has_rules(updates: list[PermissionUpdate] | None) -> bool:
    return len(extract_rules(updates)) > 0


def _context_copy(context: ToolPermissionContext) -> ToolPermissionContext:
    """Returns a shallow copy of context so mutations don't affect the original."""
    import dataclasses

    new_ctx = ToolPermissionContext.__new__(ToolPermissionContext)
    new_ctx.__dict__.update(context.__dict__)
    return new_ctx


def apply_permission_update(
    context: ToolPermissionContext,
    update: Any,
) -> ToolPermissionContext:
    """Applies a single permission update to the context and returns the updated context."""
    from optimus.utils.permissions.permission_rule_parser import (
        permission_rule_value_from_string,
        permission_rule_value_to_string,
    )

    update_type = update.get("type") if isinstance(update, dict) else getattr(update, "type", None)

    if update_type == "setMode":
        mode = update.get("mode") if isinstance(update, dict) else getattr(update, "mode", None)
        new_ctx = _context_copy(context)
        new_ctx.mode = mode
        return new_ctx

    if update_type in ("addRules", "replaceRules", "removeRules"):
        behavior = update.get("behavior") if isinstance(update, dict) else getattr(update, "behavior", None)
        destination = update.get("destination") if isinstance(update, dict) else getattr(update, "destination", None)
        rules_raw = update.get("rules", []) if isinstance(update, dict) else getattr(update, "rules", [])
        rule_strings = [
            permission_rule_value_to_string(
                r if isinstance(r, PermissionRuleValue) else PermissionRuleValue(
                    tool_name=r.get("toolName", r.get("tool_name", "")),
                    rule_content=r.get("ruleContent", r.get("rule_content")),
                )
            )
            for r in rules_raw
        ]

        rule_kind = (
            "always_allow_rules" if behavior == "allow"
            else "always_deny_rules" if behavior == "deny"
            else "always_ask_rules"
        )

        new_ctx = _context_copy(context)
        current_dict: dict[str, list[str]] = copy.deepcopy(getattr(new_ctx, rule_kind) or {})

        if update_type == "addRules":
            current_dict[destination] = current_dict.get(destination, []) + rule_strings
        elif update_type == "replaceRules":
            current_dict[destination] = rule_strings
        elif update_type == "removeRules":
            rules_to_remove = set(rule_strings)
            current_dict[destination] = [
                r for r in current_dict.get(destination, []) if r not in rules_to_remove
            ]

        setattr(new_ctx, rule_kind, current_dict)
        return new_ctx

    if update_type == "addDirectories":
        directories = update.get("directories", []) if isinstance(update, dict) else getattr(update, "directories", [])
        destination = update.get("destination") if isinstance(update, dict) else getattr(update, "destination", None)
        new_ctx = _context_copy(context)
        new_dirs = dict(new_ctx.additional_working_directories)
        for d in directories:
            new_dirs[d] = AdditionalWorkingDirectory(path=d, source=destination)
        new_ctx.additional_working_directories = new_dirs
        return new_ctx

    if update_type == "removeDirectories":
        directories = update.get("directories", []) if isinstance(update, dict) else getattr(update, "directories", [])
        new_ctx = _context_copy(context)
        new_dirs = dict(new_ctx.additional_working_directories)
        for d in directories:
            new_dirs.pop(d, None)
        new_ctx.additional_working_directories = new_dirs
        return new_ctx

    return context


def apply_permission_updates(
    context: ToolPermissionContext,
    updates: list[Any],
) -> ToolPermissionContext:
    """Applies multiple permission updates to the context."""
    updated = context
    for update in updates:
        updated = apply_permission_update(updated, update)
    return updated


def supports_persistence(destination: PermissionUpdateDestination) -> bool:
    """Returns True if the destination supports persistence to disk."""
    return destination in _EDITABLE_SOURCES


def persist_permission_update(update: Any) -> None:
    """Persists a permission update to the appropriate settings source."""
    from optimus.utils.permissions.permission_rule_parser import (
        permission_rule_value_from_string,
        permission_rule_value_to_string,
    )

    update_type = update.get("type") if isinstance(update, dict) else getattr(update, "type", None)
    destination = update.get("destination") if isinstance(update, dict) else getattr(update, "destination", None)

    if not supports_persistence(destination):
        return

    if update_type == "addRules":
        from optimus.utils.permissions.permissions_loader import add_permission_rules_to_settings

        rules_raw = update.get("rules", []) if isinstance(update, dict) else getattr(update, "rules", [])
        behavior = update.get("behavior") if isinstance(update, dict) else getattr(update, "behavior", None)
        rule_values = [
            r if isinstance(r, PermissionRuleValue) else PermissionRuleValue(
                tool_name=r.get("toolName", r.get("tool_name", "")),
                rule_content=r.get("ruleContent", r.get("rule_content")),
            )
            for r in rules_raw
        ]
        add_permission_rules_to_settings(rule_values, behavior, destination)

    elif update_type == "addDirectories":
        try:
            from optimus.utils.settings.settings import get_settings_for_source, update_settings_for_source

            directories = update.get("directories", []) if isinstance(update, dict) else getattr(update, "directories", [])
            existing = get_settings_for_source(destination)
            if isinstance(existing, dict):
                existing_dirs = existing.get("permissions", {}).get("additionalDirectories", [])
            else:
                permissions = getattr(existing, "permissions", None)
                existing_dirs = getattr(permissions, "additional_directories", []) if permissions else []
            dirs_to_add = [d for d in directories if d not in existing_dirs]
            if dirs_to_add:
                update_settings_for_source(
                    destination,
                    {"permissions": {"additionalDirectories": existing_dirs + dirs_to_add}},
                )
        except Exception:
            pass

    elif update_type == "removeRules":
        try:
            from optimus.utils.settings.settings import get_settings_for_source, update_settings_for_source

            rules_raw = update.get("rules", []) if isinstance(update, dict) else getattr(update, "rules", [])
            behavior = update.get("behavior") if isinstance(update, dict) else getattr(update, "behavior", None)
            rule_values = [
                r if isinstance(r, PermissionRuleValue) else PermissionRuleValue(
                    tool_name=r.get("toolName", r.get("tool_name", "")),
                    rule_content=r.get("ruleContent", r.get("rule_content")),
                )
                for r in rules_raw
            ]
            rules_to_remove = {permission_rule_value_to_string(rv) for rv in rule_values}
            existing = get_settings_for_source(destination)
            if isinstance(existing, dict):
                existing_rules = existing.get("permissions", {}).get(behavior, [])
            else:
                permissions = getattr(existing, "permissions", None)
                existing_rules = getattr(permissions, behavior, []) if permissions else []

            def normalize(raw: str) -> str:
                return permission_rule_value_to_string(permission_rule_value_from_string(raw))

            filtered = [r for r in existing_rules if normalize(r) not in rules_to_remove]
            update_settings_for_source(destination, {"permissions": {behavior: filtered}})
        except Exception:
            pass

    elif update_type == "removeDirectories":
        try:
            from optimus.utils.settings.settings import get_settings_for_source, update_settings_for_source

            directories = set(update.get("directories", []) if isinstance(update, dict) else getattr(update, "directories", []))
            existing = get_settings_for_source(destination)
            if isinstance(existing, dict):
                existing_dirs = existing.get("permissions", {}).get("additionalDirectories", [])
            else:
                permissions = getattr(existing, "permissions", None)
                existing_dirs = getattr(permissions, "additional_directories", []) if permissions else []
            filtered = [d for d in existing_dirs if d not in directories]
            update_settings_for_source(destination, {"permissions": {"additionalDirectories": filtered}})
        except Exception:
            pass

    elif update_type == "setMode":
        try:
            from optimus.utils.settings.settings import update_settings_for_source

            mode = update.get("mode") if isinstance(update, dict) else getattr(update, "mode", None)
            update_settings_for_source(destination, {"permissions": {"defaultMode": mode}})
        except Exception:
            pass

    elif update_type == "replaceRules":
        try:
            from optimus.utils.settings.settings import update_settings_for_source
            from optimus.utils.permissions.permission_rule_parser import permission_rule_value_to_string

            rules_raw = update.get("rules", []) if isinstance(update, dict) else getattr(update, "rules", [])
            behavior = update.get("behavior") if isinstance(update, dict) else getattr(update, "behavior", None)
            rule_values = [
                r if isinstance(r, PermissionRuleValue) else PermissionRuleValue(
                    tool_name=r.get("toolName", r.get("tool_name", "")),
                    rule_content=r.get("ruleContent", r.get("rule_content")),
                )
                for r in rules_raw
            ]
            rule_strings = [permission_rule_value_to_string(rv) for rv in rule_values]
            update_settings_for_source(destination, {"permissions": {behavior: rule_strings}})
        except Exception:
            pass


def persist_permission_updates(updates: list[Any]) -> None:
    """Persists multiple permission updates to the appropriate settings sources."""
    for update in updates:
        persist_permission_update(update)


def create_read_rule_suggestion(
    dir_path: str,
    destination: PermissionUpdateDestination = "session",
) -> Any | None:
    """Creates a Read rule suggestion for a directory.

    Returns None for the root directory (too broad).
    """
    from optimus.utils.permissions.filesystem import to_posix_path
    from pathlib import PurePosixPath

    path_for_pattern = to_posix_path(dir_path)
    if path_for_pattern == "/":
        return None

    posix = PurePosixPath(path_for_pattern)
    if posix.is_absolute():
        rule_content = "/" + str(posix) + "/**"
    else:
        rule_content = str(posix) + "/**"

    return {
        "type": "addRules",
        "rules": [{"toolName": "Read", "ruleContent": rule_content}],
        "behavior": "allow",
        "destination": destination,
    }
