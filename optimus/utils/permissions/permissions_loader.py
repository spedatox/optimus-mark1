"""
Loads permission rules from settings files.
Mirrors src/utils/permissions/permissionsLoader.ts
"""
from __future__ import annotations

from typing import Any

from optimus.types.permissions import (
    PermissionBehavior,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
)

__all__ = [
    "should_allow_managed_permission_rules_only",
    "should_show_always_allow_options",
    "load_all_permission_rules_from_disk",
    "get_permission_rules_for_source",
    "PermissionRuleFromEditableSettings",
    "delete_permission_rule_from_settings",
    "add_permission_rules_to_settings",
]

_SUPPORTED_RULE_BEHAVIORS: tuple[PermissionBehavior, ...] = ("allow", "deny", "ask")
_EDITABLE_SOURCES = ("userSettings", "projectSettings", "localSettings")

PermissionRuleFromEditableSettings = PermissionRule


def should_allow_managed_permission_rules_only() -> bool:
    """Returns True if only managed permission rules should be respected."""
    try:
        from optimus.utils.settings.settings import get_settings_for_source

        policy = get_settings_for_source("policySettings")
        return bool(policy and getattr(policy, "allow_managed_permission_rules_only", False))
    except Exception:
        return False


def should_show_always_allow_options() -> bool:
    """Returns True if 'always allow' options should be shown in permission prompts."""
    return not should_allow_managed_permission_rules_only()


def _settings_json_to_rules(data: Any, source: PermissionRuleSource) -> list[PermissionRule]:
    """Converts permissions JSON data to a list of PermissionRule objects."""
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    if not data:
        return []
    permissions = getattr(data, "permissions", None) or (data.get("permissions") if isinstance(data, dict) else None)
    if not permissions:
        return []

    rules: list[PermissionRule] = []
    for behavior in _SUPPORTED_RULE_BEHAVIORS:
        behavior_array = (
            permissions.get(behavior) if isinstance(permissions, dict)
            else getattr(permissions, behavior, None)
        )
        if behavior_array:
            for rule_string in behavior_array:
                rules.append(
                    PermissionRule(
                        source=source,
                        rule_behavior=behavior,
                        rule_value=permission_rule_value_from_string(rule_string),
                    )
                )
    return rules


def get_permission_rules_for_source(source: PermissionRuleSource) -> list[PermissionRule]:
    """Loads permission rules from a specific settings source."""
    try:
        from optimus.utils.settings.settings import get_settings_for_source

        settings = get_settings_for_source(source)
        return _settings_json_to_rules(settings, source)
    except Exception:
        return []


def load_all_permission_rules_from_disk() -> list[PermissionRule]:
    """Loads all permission rules from all relevant sources."""
    if should_allow_managed_permission_rules_only():
        return get_permission_rules_for_source("policySettings")

    rules: list[PermissionRule] = []
    try:
        from optimus.utils.settings.constants import get_enabled_setting_sources

        for source in get_enabled_setting_sources():
            rules.extend(get_permission_rules_for_source(source))
    except Exception:
        pass
    return rules


def delete_permission_rule_from_settings(rule: PermissionRuleFromEditableSettings) -> bool:
    """Deletes a rule from the settings file. Returns True on success."""
    from optimus.utils.permissions.permission_rule_parser import (
        permission_rule_value_from_string,
        permission_rule_value_to_string,
    )

    if rule.source not in _EDITABLE_SOURCES:
        return False

    try:
        from optimus.utils.settings.settings import get_settings_for_source, update_settings_for_source

        rule_string = permission_rule_value_to_string(rule.rule_value)
        settings = get_settings_for_source(rule.source)
        if not settings:
            return False

        permissions = getattr(settings, "permissions", None) or (
            settings.get("permissions") if isinstance(settings, dict) else None
        )
        if not permissions:
            return False

        behavior_array = (
            permissions.get(rule.rule_behavior) if isinstance(permissions, dict)
            else getattr(permissions, rule.rule_behavior, None)
        )
        if not behavior_array:
            return False

        def normalize_entry(raw: str) -> str:
            return permission_rule_value_to_string(permission_rule_value_from_string(raw))

        if not any(normalize_entry(r) == rule_string for r in behavior_array):
            return False

        filtered = [r for r in behavior_array if normalize_entry(r) != rule_string]
        update_settings_for_source(
            rule.source,
            {"permissions": {rule.rule_behavior: filtered}},
        )
        return True
    except Exception:
        return False


def add_permission_rules_to_settings(
    rule_values: list[PermissionRuleValue],
    rule_behavior: PermissionBehavior,
    source: str,
) -> bool:
    """Adds rules to a settings file. Returns True on success."""
    from optimus.utils.permissions.permission_rule_parser import (
        permission_rule_value_from_string,
        permission_rule_value_to_string,
    )

    if should_allow_managed_permission_rules_only():
        return False

    if not rule_values:
        return True

    rule_strings = [permission_rule_value_to_string(rv) for rv in rule_values]

    try:
        from optimus.utils.settings.settings import get_settings_for_source, update_settings_for_source

        settings = get_settings_for_source(source) or {}
        if isinstance(settings, dict):
            permissions = settings.get("permissions", {})
        else:
            permissions = getattr(settings, "permissions", None) or {}
        if isinstance(permissions, dict):
            existing_rules = list(permissions.get(rule_behavior, []))
        else:
            existing_rules = list(getattr(permissions, rule_behavior, None) or [])

        existing_normalized = {
            permission_rule_value_to_string(permission_rule_value_from_string(r))
            for r in existing_rules
        }
        new_rules = [r for r in rule_strings if r not in existing_normalized]

        if not new_rules:
            return True

        update_settings_for_source(
            source,
            {"permissions": {rule_behavior: existing_rules + new_rules}},
        )
        return True
    except Exception:
        return False
