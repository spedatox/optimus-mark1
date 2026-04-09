"""
Permission context setup and mode transition logic.
Mirrors src/utils/permissions/permissionSetup.ts
"""
from __future__ import annotations

import os
from typing import Any, Callable

from optimus.types.permissions import (
    PermissionMode,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
    ToolPermissionContext,
)

__all__ = [
    "is_dangerous_bash_permission",
    "is_dangerous_power_shell_permission",
    "is_dangerous_task_permission",
    "find_dangerous_classifier_permissions",
    "is_overly_broad_bash_allow_rule",
    "is_overly_broad_power_shell_allow_rule",
    "find_overly_broad_bash_permissions",
    "find_overly_broad_power_shell_permissions",
    "remove_dangerous_permissions",
    "strip_dangerous_permissions_for_auto_mode",
    "restore_dangerous_permissions",
    "transition_permission_mode",
    "initial_permission_mode_from_cli",
    "apply_permission_rules_to_permission_context",
    "should_disable_bypass_permissions",
    "is_auto_mode_gate_enabled",
    "get_auto_mode_unavailable_reason",
    "verify_auto_mode_gate_access",
    "create_disabled_bypass_permissions_context",
    "DangerousPermissionInfo",
]

BASH_TOOL_NAME = "Bash"
POWERSHELL_TOOL_NAME = "PowerShell"
AGENT_TOOL_NAME = "Agent"

_USER_TYPE = os.environ.get("USER_TYPE", "")


class DangerousPermissionInfo:
    def __init__(
        self,
        rule_value: PermissionRuleValue,
        source: PermissionRuleSource,
        rule_display: str,
        source_display: str,
    ) -> None:
        self.rule_value = rule_value
        self.source = source
        self.rule_display = rule_display
        self.source_display = source_display


def is_dangerous_bash_permission(tool_name: str, rule_content: str | None) -> bool:
    """Returns True if a Bash permission rule would bypass auto mode classifier."""
    from optimus.utils.permissions.dangerous_patterns import DANGEROUS_BASH_PATTERNS

    if tool_name != BASH_TOOL_NAME:
        return False

    if rule_content is None or rule_content == "":
        return True

    content = rule_content.strip().lower()

    if content == "*":
        return True

    for pattern in DANGEROUS_BASH_PATTERNS:
        lp = pattern.lower()
        if content == lp:
            return True
        if content == f"{lp}:*":
            return True
        if content == f"{lp}*":
            return True
        if content == f"{lp} *":
            return True
        if content.startswith(f"{lp} -") and content.endswith("*"):
            return True

    return False


def is_dangerous_power_shell_permission(tool_name: str, rule_content: str | None) -> bool:
    """Returns True if a PowerShell permission rule would bypass auto mode classifier."""
    from optimus.utils.permissions.dangerous_patterns import CROSS_PLATFORM_CODE_EXEC

    if tool_name != POWERSHELL_TOOL_NAME:
        return False

    if rule_content is None or rule_content == "":
        return True

    content = rule_content.strip().lower()

    if content == "*":
        return True

    patterns = list(CROSS_PLATFORM_CODE_EXEC) + [
        "pwsh",
        "powershell",
        "cmd",
        "wsl",
        "iex",
        "invoke-expression",
        "icm",
        "invoke-command",
        "start-process",
        "saps",
        "start",
        "start-job",
        "sajb",
        "start-threadjob",
        "register-objectevent",
        "register-engineevent",
        "register-wmievent",
        "register-scheduledjob",
        "new-pssession",
        "nsn",
        "enter-pssession",
        "etsn",
        "add-type",
        "new-object",
    ]

    for pattern in patterns:
        lp = pattern.lower()
        if content in (lp, f"{lp}:*", f"{lp}*", f"{lp} *"):
            return True
        if content.startswith(f"{lp} -") and content.endswith("*"):
            return True
        # .exe variant
        sp = lp.find(" ")
        exe = f"{lp[:sp]}.exe{lp[sp:]}" if sp != -1 else f"{lp}.exe"
        if content in (exe, f"{exe}:*", f"{exe}*", f"{exe} *"):
            return True
        if content.startswith(f"{exe} -") and content.endswith("*"):
            return True

    return False


def is_dangerous_task_permission(tool_name: str, rule_content: str | None) -> bool:
    """Returns True if an Agent allow rule would bypass classifier evaluation."""
    from optimus.utils.permissions.permission_rule_parser import normalize_legacy_tool_name

    return normalize_legacy_tool_name(tool_name) == AGENT_TOOL_NAME


def _is_dangerous_classifier_permission(tool_name: str, rule_content: str | None) -> bool:
    if _USER_TYPE == "ant" and tool_name == "Tmux":
        return True
    return (
        is_dangerous_bash_permission(tool_name, rule_content)
        or is_dangerous_power_shell_permission(tool_name, rule_content)
        or is_dangerous_task_permission(tool_name, rule_content)
    )


def _format_permission_source(source: PermissionRuleSource) -> str:
    try:
        from optimus.utils.settings.constants import SETTING_SOURCES
        from optimus.utils.settings.settings import get_settings_file_path_for_source
        from optimus.utils.cwd import get_cwd
        import os

        if source in SETTING_SOURCES:
            file_path = get_settings_file_path_for_source(source)
            if file_path:
                try:
                    rel = os.path.relpath(file_path, get_cwd())
                    return rel if len(rel) < len(file_path) else file_path
                except ValueError:
                    return file_path
    except Exception:
        pass
    return source


def find_dangerous_classifier_permissions(
    rules: list[PermissionRule],
    cli_allowed_tools: list[str],
) -> list[DangerousPermissionInfo]:
    """Finds all dangerous permissions from rules and CLI arguments."""
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    dangerous: list[DangerousPermissionInfo] = []

    for rule in rules:
        if rule.rule_behavior == "allow" and _is_dangerous_classifier_permission(
            rule.rule_value.tool_name, rule.rule_value.rule_content
        ):
            if rule.rule_value.rule_content:
                display = f"{rule.rule_value.tool_name}({rule.rule_value.rule_content})"
            else:
                display = f"{rule.rule_value.tool_name}(*)"
            dangerous.append(
                DangerousPermissionInfo(
                    rule_value=rule.rule_value,
                    source=rule.source,
                    rule_display=display,
                    source_display=_format_permission_source(rule.source),
                )
            )

    import re as _re

    for tool_spec in cli_allowed_tools:
        m = _re.match(r"^([^(]+)(?:\(([^)]*)\))?$", tool_spec)
        if m:
            tool_name = m.group(1).strip()
            rule_content = m.group(2).strip() if m.group(2) else None
            if _is_dangerous_classifier_permission(tool_name, rule_content):
                display = tool_spec if rule_content else f"{tool_name}(*)"
                dangerous.append(
                    DangerousPermissionInfo(
                        rule_value=PermissionRuleValue(tool_name=tool_name, rule_content=rule_content),
                        source="cliArg",
                        rule_display=display,
                        source_display="--allowed-tools",
                    )
                )

    return dangerous


def is_overly_broad_bash_allow_rule(rule_value: PermissionRuleValue) -> bool:
    """Returns True for tool-level Bash allow rules with no content restriction."""
    return rule_value.tool_name == BASH_TOOL_NAME and rule_value.rule_content is None


def is_overly_broad_power_shell_allow_rule(rule_value: PermissionRuleValue) -> bool:
    """Returns True for tool-level PowerShell allow rules with no content restriction."""
    return rule_value.tool_name == POWERSHELL_TOOL_NAME and rule_value.rule_content is None


def find_overly_broad_bash_permissions(
    rules: list[PermissionRule],
    cli_allowed_tools: list[str],
) -> list[DangerousPermissionInfo]:
    """Finds all overly broad Bash allow rules."""
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    overly_broad: list[DangerousPermissionInfo] = []

    for rule in rules:
        if rule.rule_behavior == "allow" and is_overly_broad_bash_allow_rule(rule.rule_value):
            overly_broad.append(
                DangerousPermissionInfo(
                    rule_value=rule.rule_value,
                    source=rule.source,
                    rule_display=f"{BASH_TOOL_NAME}(*)",
                    source_display=_format_permission_source(rule.source),
                )
            )

    for tool_spec in cli_allowed_tools:
        parsed = permission_rule_value_from_string(tool_spec)
        if is_overly_broad_bash_allow_rule(parsed):
            overly_broad.append(
                DangerousPermissionInfo(
                    rule_value=parsed,
                    source="cliArg",
                    rule_display=f"{BASH_TOOL_NAME}(*)",
                    source_display="--allowed-tools",
                )
            )

    return overly_broad


def find_overly_broad_power_shell_permissions(
    rules: list[PermissionRule],
    cli_allowed_tools: list[str],
) -> list[DangerousPermissionInfo]:
    """Finds all overly broad PowerShell allow rules."""
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    overly_broad: list[DangerousPermissionInfo] = []

    for rule in rules:
        if rule.rule_behavior == "allow" and is_overly_broad_power_shell_allow_rule(rule.rule_value):
            overly_broad.append(
                DangerousPermissionInfo(
                    rule_value=rule.rule_value,
                    source=rule.source,
                    rule_display=f"{POWERSHELL_TOOL_NAME}(*)",
                    source_display=_format_permission_source(rule.source),
                )
            )

    for tool_spec in cli_allowed_tools:
        parsed = permission_rule_value_from_string(tool_spec)
        if is_overly_broad_power_shell_allow_rule(parsed):
            overly_broad.append(
                DangerousPermissionInfo(
                    rule_value=parsed,
                    source="cliArg",
                    rule_display=f"{POWERSHELL_TOOL_NAME}(*)",
                    source_display="--allowed-tools",
                )
            )

    return overly_broad


def _is_permission_update_destination(source: PermissionRuleSource) -> bool:
    return source in ("userSettings", "projectSettings", "localSettings", "session", "cliArg")


def remove_dangerous_permissions(
    context: ToolPermissionContext,
    dangerous_permissions: list[DangerousPermissionInfo],
) -> ToolPermissionContext:
    """Removes dangerous permissions from the in-memory context."""
    from optimus.utils.permissions.permission_update import apply_permission_update
    from optimus.types.permissions import PermissionUpdateDestination

    rules_by_source: dict[str, list[PermissionRuleValue]] = {}
    for perm in dangerous_permissions:
        if not _is_permission_update_destination(perm.source):
            continue
        rules_by_source.setdefault(perm.source, []).append(perm.rule_value)

    updated = context
    for destination, rules in rules_by_source.items():
        updated = apply_permission_update(
            updated,
            {
                "type": "removeRules",
                "rules": [{"toolName": rv.tool_name, "ruleContent": rv.rule_content} for rv in rules],
                "behavior": "allow",
                "destination": destination,
            },
        )
    return updated


def strip_dangerous_permissions_for_auto_mode(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """Strips dangerous permissions from the context for auto mode."""
    from optimus.utils.permissions.permission_rule_parser import (
        permission_rule_value_from_string,
        permission_rule_value_to_string,
    )

    rules: list[PermissionRule] = []
    for source, rule_strings in (context.always_allow_rules or {}).items():
        if not rule_strings:
            continue
        for rs in rule_strings:
            rv = permission_rule_value_from_string(rs)
            rules.append(
                PermissionRule(
                    source=source,  # type: ignore[arg-type]
                    rule_behavior="allow",
                    rule_value=rv,
                )
            )

    dangerous = find_dangerous_classifier_permissions(rules, [])
    if not dangerous:
        from optimus.utils.permissions.permission_update import _context_copy
        new_ctx = _context_copy(context)
        new_ctx.stripped_dangerous_rules = new_ctx.stripped_dangerous_rules or {}
        return new_ctx

    stripped: dict[str, list[str]] = {}
    for perm in dangerous:
        if not _is_permission_update_destination(perm.source):
            continue
        stripped.setdefault(perm.source, []).append(
            permission_rule_value_to_string(perm.rule_value)
        )

    cleaned = remove_dangerous_permissions(context, dangerous)
    from optimus.utils.permissions.permission_update import _context_copy
    new_ctx = _context_copy(cleaned)
    new_ctx.stripped_dangerous_rules = stripped
    return new_ctx


def restore_dangerous_permissions(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """Restores dangerous allow rules previously stashed by strip_dangerous_permissions_for_auto_mode."""
    from optimus.utils.permissions.permission_update import apply_permission_update, _context_copy
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    stash = context.stripped_dangerous_rules
    if not stash:
        return context

    result = context
    for source, rule_strings in stash.items():
        if not rule_strings:
            continue
        rule_values = [permission_rule_value_from_string(rs) for rs in rule_strings]
        result = apply_permission_update(
            result,
            {
                "type": "addRules",
                "rules": [{"toolName": rv.tool_name, "ruleContent": rv.rule_content} for rv in rule_values],
                "behavior": "allow",
                "destination": source,
            },
        )

    new_ctx = _context_copy(result)
    new_ctx.stripped_dangerous_rules = None
    return new_ctx


def transition_permission_mode(
    from_mode: str,
    to_mode: str,
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """Handles all state transitions when switching permission modes."""
    from optimus.utils.permissions.permission_update import _context_copy

    if from_mode == to_mode:
        return context

    try:
        from optimus.bootstrap.state import (
            handle_auto_mode_transition,
            handle_plan_mode_transition,
            set_has_exited_plan_mode,
            set_needs_auto_mode_exit_attachment,
        )
        handle_plan_mode_transition(from_mode, to_mode)
        handle_auto_mode_transition(from_mode, to_mode)
        if from_mode == "plan" and to_mode != "plan":
            set_has_exited_plan_mode(True)
    except Exception:
        pass

    from optimus.utils.features import is_feature_enabled

    if is_feature_enabled("TRANSCRIPT_CLASSIFIER"):
        if to_mode == "plan" and from_mode != "plan":
            return _prepare_context_for_plan_mode(context)

        try:
            from optimus.utils.permissions.auto_mode_state import is_auto_mode_active

            from_uses_classifier = from_mode == "auto" or (
                from_mode == "plan" and is_auto_mode_active()
            )
        except Exception:
            from_uses_classifier = from_mode == "auto"

        to_uses_classifier = to_mode == "auto"

        if to_uses_classifier and not from_uses_classifier:
            if not is_auto_mode_gate_enabled():
                raise ValueError("Cannot transition to auto mode: gate is not enabled")
            try:
                from optimus.utils.permissions.auto_mode_state import set_auto_mode_active
                set_auto_mode_active(True)
            except Exception:
                pass
            context = strip_dangerous_permissions_for_auto_mode(context)
        elif from_uses_classifier and not to_uses_classifier:
            try:
                from optimus.utils.permissions.auto_mode_state import set_auto_mode_active
                set_auto_mode_active(False)
                from optimus.bootstrap.state import set_needs_auto_mode_exit_attachment
                set_needs_auto_mode_exit_attachment(True)
            except Exception:
                pass
            context = restore_dangerous_permissions(context)

    if from_mode == "plan" and to_mode != "plan" and context.pre_plan_mode:
        new_ctx = _context_copy(context)
        new_ctx.pre_plan_mode = None
        return new_ctx

    return context


def _prepare_context_for_plan_mode(context: ToolPermissionContext) -> ToolPermissionContext:
    """Prepares context for plan mode entry."""
    from optimus.utils.permissions.permission_update import _context_copy

    new_ctx = _context_copy(context)
    new_ctx.pre_plan_mode = context.mode
    return new_ctx


def apply_permission_rules_to_permission_context(
    context: ToolPermissionContext,
    rules: list[PermissionRule],
) -> ToolPermissionContext:
    """Applies a list of permission rules to the context."""
    from optimus.utils.permissions.permission_update import apply_permission_update

    for rule in rules:
        context = apply_permission_update(
            context,
            {
                "type": "addRules",
                "rules": [
                    {
                        "toolName": rule.rule_value.tool_name,
                        "ruleContent": rule.rule_value.rule_content,
                    }
                ],
                "behavior": rule.rule_behavior,
                "destination": rule.source if _is_permission_update_destination(rule.source) else "session",
            },
        )
    return context


def initial_permission_mode_from_cli(
    permission_mode_cli: str | None,
    dangerously_skip_permissions: bool | None,
) -> dict[str, Any]:
    """Converts CLI flags to an initial PermissionMode."""
    from optimus.utils.permissions.permission_mode import permission_mode_from_string

    if dangerously_skip_permissions:
        return {"mode": "bypassPermissions"}

    if permission_mode_cli:
        mode = permission_mode_from_string(permission_mode_cli)
        return {"mode": mode}

    return {"mode": "default"}


async def should_disable_bypass_permissions() -> bool:
    """Returns True if bypassPermissions mode should be disabled via Statsig gate."""
    try:
        from optimus.services.analytics.growthbook import check_statsig_feature_gate

        return await check_statsig_feature_gate("tengu_disable_bypass_permissions_mode")
    except Exception:
        return False


def is_auto_mode_gate_enabled() -> bool:
    """Returns True if the auto mode gate is enabled (synchronous cached check)."""
    try:
        from optimus.utils.permissions.auto_mode_state import is_auto_mode_circuit_broken

        if is_auto_mode_circuit_broken():
            return False
    except Exception:
        pass
    return False  # Auto mode is ant-only / feature-gated; disabled by default


def get_auto_mode_unavailable_reason() -> str:
    """Returns a human-readable reason why auto mode is unavailable."""
    try:
        from optimus.utils.permissions.auto_mode_state import is_auto_mode_circuit_broken

        if is_auto_mode_circuit_broken():
            return "Auto mode circuit breaker triggered (gate returned 'disabled')"
    except Exception:
        pass
    return "Auto mode is not available (TRANSCRIPT_CLASSIFIER feature is not enabled)"


async def verify_auto_mode_gate_access(
    context: ToolPermissionContext,
    fast_mode: bool | None = None,
) -> tuple[Callable[[ToolPermissionContext], ToolPermissionContext], str | None]:
    """Verifies auto mode gate access and returns (context_updater, notification).

    The context_updater is a function that takes the current context and returns
    an updated context. The notification is an optional message to show the user.
    """
    # Auto mode is always unavailable in the external build
    return lambda ctx: ctx, None


def create_disabled_bypass_permissions_context(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """Returns a copy of context with bypassPermissions mode disabled."""
    from optimus.utils.permissions.permission_update import _context_copy

    new_ctx = _context_copy(context)
    new_ctx.is_bypass_permissions_mode_available = False
    if new_ctx.mode == "bypassPermissions":
        new_ctx.mode = "default"
    return new_ctx
