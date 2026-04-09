"""
Detection of unreachable (shadowed) permission rules.
Mirrors src/utils/permissions/shadowedRuleDetection.ts
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from optimus.types.permissions import PermissionRule, PermissionRuleSource, ToolPermissionContext

__all__ = [
    "ShadowType",
    "UnreachableRule",
    "DetectUnreachableRulesOptions",
    "is_shared_setting_source",
    "detect_unreachable_rules",
]

ShadowType = Literal["ask", "deny"]

BASH_TOOL_NAME = "Bash"


@dataclass
class UnreachableRule:
    rule: PermissionRule
    reason: str
    shadowed_by: PermissionRule
    shadow_type: ShadowType
    fix: str


@dataclass
class DetectUnreachableRulesOptions:
    sandbox_auto_allow_enabled: bool = False


def is_shared_setting_source(source: PermissionRuleSource) -> bool:
    """Returns True if the source is shared (visible to other users)."""
    return source in ("projectSettings", "policySettings", "command")


def _format_source(source: PermissionRuleSource) -> str:
    from optimus.utils.permissions.permissions import permission_rule_source_display_string
    return permission_rule_source_display_string(source)


def _generate_fix_suggestion(
    shadow_type: ShadowType,
    shadowing_rule: PermissionRule,
    shadowed_rule: PermissionRule,
) -> str:
    shadowing_source = _format_source(shadowing_rule.source)
    shadowed_source = _format_source(shadowed_rule.source)
    tool_name = shadowing_rule.rule_value.tool_name

    if shadow_type == "deny":
        return (
            f'Remove the "{tool_name}" deny rule from {shadowing_source}, '
            f"or remove the specific allow rule from {shadowed_source}"
        )
    return (
        f'Remove the "{tool_name}" ask rule from {shadowing_source}, '
        f"or remove the specific allow rule from {shadowed_source}"
    )


def _is_allow_rule_shadowed_by_ask_rule(
    allow_rule: PermissionRule,
    ask_rules: list[PermissionRule],
    options: DetectUnreachableRulesOptions,
) -> tuple[bool, PermissionRule | None]:
    """Returns (is_shadowed, shadowing_rule)."""
    tool_name = allow_rule.rule_value.tool_name
    rule_content = allow_rule.rule_value.rule_content

    # Only check allow rules that have specific content
    if rule_content is None:
        return False, None

    # Find any tool-wide ask rule for the same tool
    shadowing_ask_rule = next(
        (
            r
            for r in ask_rules
            if r.rule_value.tool_name == tool_name and r.rule_value.rule_content is None
        ),
        None,
    )

    if shadowing_ask_rule is None:
        return False, None

    # Special case: Bash with sandbox auto-allow from personal settings
    if tool_name == BASH_TOOL_NAME and options.sandbox_auto_allow_enabled:
        if not is_shared_setting_source(shadowing_ask_rule.source):
            return False, None

    return True, shadowing_ask_rule


def _is_allow_rule_shadowed_by_deny_rule(
    allow_rule: PermissionRule,
    deny_rules: list[PermissionRule],
) -> tuple[bool, PermissionRule | None]:
    """Returns (is_shadowed, shadowing_rule)."""
    tool_name = allow_rule.rule_value.tool_name
    rule_content = allow_rule.rule_value.rule_content

    if rule_content is None:
        return False, None

    shadowing_deny_rule = next(
        (
            r
            for r in deny_rules
            if r.rule_value.tool_name == tool_name and r.rule_value.rule_content is None
        ),
        None,
    )

    if shadowing_deny_rule is None:
        return False, None

    return True, shadowing_deny_rule


def detect_unreachable_rules(
    context: ToolPermissionContext,
    options: DetectUnreachableRulesOptions,
) -> list[UnreachableRule]:
    """Detect all unreachable permission rules in the given context."""
    from optimus.utils.permissions.permissions import get_allow_rules, get_ask_rules, get_deny_rules

    unreachable: list[UnreachableRule] = []
    allow_rules = get_allow_rules(context)
    ask_rules = get_ask_rules(context)
    deny_rules = get_deny_rules(context)

    for allow_rule in allow_rules:
        # Check deny shadowing first (more severe)
        deny_shadowed, deny_shadowing = _is_allow_rule_shadowed_by_deny_rule(allow_rule, deny_rules)
        if deny_shadowed and deny_shadowing is not None:
            shadow_source = _format_source(deny_shadowing.source)
            unreachable.append(
                UnreachableRule(
                    rule=allow_rule,
                    reason=f'Blocked by "{deny_shadowing.rule_value.tool_name}" deny rule (from {shadow_source})',
                    shadowed_by=deny_shadowing,
                    shadow_type="deny",
                    fix=_generate_fix_suggestion("deny", deny_shadowing, allow_rule),
                )
            )
            continue

        # Check ask shadowing
        ask_shadowed, ask_shadowing = _is_allow_rule_shadowed_by_ask_rule(allow_rule, ask_rules, options)
        if ask_shadowed and ask_shadowing is not None:
            shadow_source = _format_source(ask_shadowing.source)
            unreachable.append(
                UnreachableRule(
                    rule=allow_rule,
                    reason=f'Shadowed by "{ask_shadowing.rule_value.tool_name}" ask rule (from {shadow_source})',
                    shadowed_by=ask_shadowing,
                    shadow_type="ask",
                    fix=_generate_fix_suggestion("ask", ask_shadowing, allow_rule),
                )
            )

    return unreachable
