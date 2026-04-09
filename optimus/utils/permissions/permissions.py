"""
Core permissions checking logic.
Mirrors src/utils/permissions/permissions.ts
"""
from __future__ import annotations

import os
from typing import Any

from optimus.types.permissions import (
    PermissionAskDecision,
    PermissionAllowDecision,
    PermissionDenyDecision,
    PermissionBehavior,
    PermissionDecision,
    PermissionDecisionReason,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
    ToolPermissionContext,
)

__all__ = [
    "permission_rule_source_display_string",
    "get_allow_rules",
    "get_deny_rules",
    "get_ask_rules",
    "create_permission_request_message",
    "tool_always_allowed_rule",
    "get_deny_rule_for_tool",
    "get_ask_rule_for_tool",
    "get_deny_rule_for_agent",
    "filter_denied_agents",
    "get_rule_by_contents_for_tool",
    "get_rule_by_contents_for_tool_name",
    "has_permissions_to_use_tool",
    "apply_permission_rules_to_permission_context",
]

_PERMISSION_RULE_SOURCES: tuple[PermissionRuleSource, ...] = (
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
)


def permission_rule_source_display_string(source: PermissionRuleSource) -> str:
    """Returns a human-readable display string for a permission rule source."""
    try:
        from optimus.utils.settings.constants import get_setting_source_display_name_lowercase

        return get_setting_source_display_name_lowercase(source)
    except Exception:
        return source


def _rules_from_context_by_kind(
    context: ToolPermissionContext,
    rule_kind_attr: str,
    rule_behavior: PermissionBehavior,
) -> list[PermissionRule]:
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_from_string

    rules_by_source: dict[str, list[str]] = getattr(context, rule_kind_attr) or {}
    result: list[PermissionRule] = []
    for source in _PERMISSION_RULE_SOURCES:
        for rule_string in rules_by_source.get(source, []):
            result.append(
                PermissionRule(
                    source=source,
                    rule_behavior=rule_behavior,
                    rule_value=permission_rule_value_from_string(rule_string),
                )
            )
    return result


def get_allow_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _rules_from_context_by_kind(context, "always_allow_rules", "allow")


def get_deny_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _rules_from_context_by_kind(context, "always_deny_rules", "deny")


def get_ask_rules(context: ToolPermissionContext) -> list[PermissionRule]:
    return _rules_from_context_by_kind(context, "always_ask_rules", "ask")


def _get_tool_name_for_permission_check(tool: Any) -> str:
    """Returns the name to use for permission rule matching.
    MCP tools use their fully qualified mcp__server__tool name.
    """
    mcp_info = getattr(tool, "mcp_info", None)
    if mcp_info is not None:
        server = getattr(mcp_info, "server_name", None)
        tool_name = getattr(mcp_info, "tool_name", None)
        if server and tool_name:
            return f"mcp__{server}__{tool_name}"
        if server:
            return f"mcp__{server}"
    return getattr(tool, "name", str(tool))


def _tool_matches_rule(tool: Any, rule: PermissionRule) -> bool:
    """Returns True if the rule applies to this tool (whole-tool match)."""
    if rule.rule_value.rule_content is not None:
        return False

    name_for_match = _get_tool_name_for_permission_check(tool)

    if rule.rule_value.tool_name == name_for_match:
        return True

    # MCP server-level permission: rule "mcp__server1" matches "mcp__server1__tool1"
    rule_parts = rule.rule_value.tool_name.split("__")
    tool_parts = name_for_match.split("__")
    if (
        len(rule_parts) >= 2
        and rule_parts[0] == "mcp"
        and len(tool_parts) >= 3
        and tool_parts[0] == "mcp"
        and rule_parts[1] == tool_parts[1]
        and (len(rule_parts) == 2 or rule_parts[2] in ("", "*"))
    ):
        return True

    return False


def tool_always_allowed_rule(
    context: ToolPermissionContext,
    tool: Any,
) -> PermissionRule | None:
    """Returns the allow rule that covers the entire tool, or None."""
    return next(
        (r for r in get_allow_rules(context) if _tool_matches_rule(tool, r)),
        None,
    )


def get_deny_rule_for_tool(
    context: ToolPermissionContext,
    tool: Any,
) -> PermissionRule | None:
    """Returns the deny rule that covers the entire tool, or None."""
    return next(
        (r for r in get_deny_rules(context) if _tool_matches_rule(tool, r)),
        None,
    )


def get_ask_rule_for_tool(
    context: ToolPermissionContext,
    tool: Any,
) -> PermissionRule | None:
    """Returns the ask rule that covers the entire tool, or None."""
    return next(
        (r for r in get_ask_rules(context) if _tool_matches_rule(tool, r)),
        None,
    )


def get_deny_rule_for_agent(
    context: ToolPermissionContext,
    agent_tool_name: str,
    agent_type: str,
) -> PermissionRule | None:
    """Returns the deny rule for a specific agent type, or None."""
    return next(
        (
            r
            for r in get_deny_rules(context)
            if r.rule_value.tool_name == agent_tool_name
            and r.rule_value.rule_content == agent_type
        ),
        None,
    )


def filter_denied_agents(
    agents: list[Any],
    context: ToolPermissionContext,
    agent_tool_name: str,
) -> list[Any]:
    """Filter agents to exclude those that are denied via Agent(agentType) syntax."""
    denied_types: set[str] = set()
    for rule in get_deny_rules(context):
        if (
            rule.rule_value.tool_name == agent_tool_name
            and rule.rule_value.rule_content is not None
        ):
            denied_types.add(rule.rule_value.rule_content)
    return [a for a in agents if a.agent_type not in denied_types]


def get_rule_by_contents_for_tool(
    context: ToolPermissionContext,
    tool: Any,
    behavior: PermissionBehavior,
) -> dict[str, PermissionRule]:
    """Returns a map of rule contents to PermissionRule for the given tool."""
    return get_rule_by_contents_for_tool_name(
        context, _get_tool_name_for_permission_check(tool), behavior
    )


def get_rule_by_contents_for_tool_name(
    context: ToolPermissionContext,
    tool_name: str,
    behavior: PermissionBehavior,
) -> dict[str, PermissionRule]:
    """Returns a map of rule contents to PermissionRule for the given tool name."""
    rules: list[PermissionRule]
    if behavior == "allow":
        rules = get_allow_rules(context)
    elif behavior == "deny":
        rules = get_deny_rules(context)
    else:
        rules = get_ask_rules(context)

    result: dict[str, PermissionRule] = {}
    for rule in rules:
        if (
            rule.rule_value.tool_name == tool_name
            and rule.rule_value.rule_content is not None
            and rule.rule_behavior == behavior
        ):
            result[rule.rule_value.rule_content] = rule
    return result


def create_permission_request_message(
    tool_name: str,
    decision_reason: PermissionDecisionReason | None = None,
) -> str:
    """Creates a permission request message explaining the permission request."""
    from optimus.utils.permissions.permission_rule_parser import permission_rule_value_to_string
    from optimus.utils.permissions.permission_mode import permission_mode_title

    if decision_reason:
        reason_type = decision_reason.get("type") if isinstance(decision_reason, dict) else None

        if reason_type == "classifier":
            classifier = decision_reason.get("classifier", "")
            reason = decision_reason.get("reason", "")
            return f"Classifier '{classifier}' requires approval for this {tool_name} command: {reason}"

        if reason_type == "hook":
            hook_name = decision_reason.get("hookName", "")
            reason = decision_reason.get("reason")
            if reason:
                return f"Hook '{hook_name}' blocked this action: {reason}"
            return f"Hook '{hook_name}' requires approval for this {tool_name} command"

        if reason_type == "rule":
            rule = decision_reason.get("rule")
            if rule:
                rule_value = getattr(rule, "rule_value", None) or rule.get("rule_value") if isinstance(rule, dict) else None
                source = getattr(rule, "source", None) or rule.get("source") if isinstance(rule, dict) else None
                if rule_value:
                    rule_string = permission_rule_value_to_string(rule_value) if hasattr(rule_value, "tool_name") else str(rule_value)
                    source_str = permission_rule_source_display_string(source) if source else "unknown"
                    return f"Permission rule '{rule_string}' from {source_str} requires approval for this {tool_name} command"

        if reason_type == "subcommandResults":
            reasons = decision_reason.get("reasons", [])
            needs_approval = [
                cmd
                for cmd, result in (reasons if isinstance(reasons, list) else reasons.items() if hasattr(reasons, "items") else [])
                if (getattr(result, "behavior", None) or result.get("behavior") if isinstance(result, dict) else None) in ("ask", "passthrough")
            ]
            if needs_approval:
                n = len(needs_approval)
                parts_str = ", ".join(needs_approval)
                part_word = "part" if n == 1 else "parts"
                req_word = "requires" if n == 1 else "require"
                return f"This {tool_name} command contains multiple operations. The following {part_word} {req_word} approval: {parts_str}"
            return f"This {tool_name} command contains multiple operations that require approval"

        if reason_type == "permissionPromptTool":
            prompt_tool = decision_reason.get("permissionPromptToolName", "")
            return f"Tool '{prompt_tool}' requires approval for this {tool_name} command"

        if reason_type == "sandboxOverride":
            return "Run outside of the sandbox"

        if reason_type == "workingDir":
            return decision_reason.get("reason", f"Claude requested permissions to use {tool_name}.")

        if reason_type in ("safetyCheck", "other", "asyncAgent"):
            return decision_reason.get("reason", f"Claude requested permissions to use {tool_name}.")

        if reason_type == "mode":
            mode = decision_reason.get("mode", "")
            mode_title = permission_mode_title(mode)
            return f"Current permission mode ({mode_title}) requires approval for this {tool_name} command"

    return f"Claude requested permissions to use {tool_name}, but you haven't granted it yet."


def apply_permission_rules_to_permission_context(
    context: ToolPermissionContext,
    rules: list[PermissionRule],
) -> ToolPermissionContext:
    """Applies permission rules to the context, returning the updated context."""
    from optimus.utils.permissions.permission_update import apply_permission_update

    for rule in rules:
        dest = rule.source if rule.source in (
            "userSettings", "projectSettings", "localSettings", "session", "cliArg"
        ) else "session"
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
                "destination": dest,
            },
        )
    return context


async def has_permissions_to_use_tool(
    tool: Any,
    input_data: dict[str, Any],
    context: Any,
    assistant_message: Any | None = None,
    tool_use_id: str = "",
) -> PermissionDecision:
    """Main entry point for checking if a tool can be used.

    This is the Python port of hasPermissionsToUseTool from permissions.ts.
    It checks rules, mode, and (when enabled) classifiers.
    """
    from optimus.utils.permissions.denial_tracking import (
        create_denial_tracking_state,
        record_denial,
        record_success,
        should_fallback_to_prompting,
    )

    app_state = context.get_app_state()
    tool_permission_context: ToolPermissionContext = app_state.tool_permission_context
    mode = tool_permission_context.mode

    # 1. Plan mode: deny everything that writes
    if mode == "plan":
        result = await _check_plan_mode(tool, input_data, context)
        if result:
            return result

    # 2. bypassPermissions: allow everything (checked in tool.check_permissions)
    # 3. Run the tool's own permission check
    try:
        parsed_input = tool.input_schema.parse(input_data) if hasattr(tool, "input_schema") else input_data
        result = await _run_tool_check_permissions(tool, parsed_input, context)
    except Exception:
        result = PermissionAskDecision(
            message=create_permission_request_message(tool.name),
        )

    # 4. Always-allow rules (tool level)
    if result.behavior == "allow":
        if mode == "auto":
            _try_record_success(context)
        return result

    # 5. Auto-deny for dontAsk mode
    if result.behavior == "ask" and mode == "dontAsk":
        from optimus.utils.messages import DONT_ASK_REJECT_MESSAGE
        return PermissionDenyDecision(
            message=DONT_ASK_REJECT_MESSAGE(tool.name),
            decision_reason={"type": "mode", "mode": "dontAsk"},
        )

    # 6. Auto mode: run classifier
    if result.behavior == "ask" and mode == "auto":
        return await _handle_auto_mode(tool, input_data, context, result, tool_use_id, assistant_message)

    # 7. For headless agents (shouldAvoidPermissionPrompts), auto-deny
    if result.behavior == "ask" and getattr(tool_permission_context, "should_avoid_permission_prompts", False):
        # Run hooks first
        hook_result = await _run_permission_request_hooks_headless(tool, input_data, tool_use_id, context)
        if hook_result:
            return hook_result
        return PermissionDenyDecision(
            message=getattr(result, "message", create_permission_request_message(tool.name)),
            decision_reason={"type": "asyncAgent", "reason": "Permission prompts are not available in headless mode"},
        )

    return result


async def _check_plan_mode(tool: Any, input_data: dict, context: Any) -> PermissionDecision | None:
    """In plan mode, only allow read-only tools."""
    return None  # Delegate to tool.check_permissions


async def _run_tool_check_permissions(tool: Any, parsed_input: Any, context: Any) -> PermissionDecision:
    """Calls tool.check_permissions and returns the result."""
    check_fn = getattr(tool, "check_permissions", None)
    if check_fn is None:
        return PermissionAskDecision(message=create_permission_request_message(getattr(tool, "name", "unknown")))
    import asyncio

    if asyncio.iscoroutinefunction(check_fn):
        result = await check_fn(parsed_input, context)
    else:
        result = check_fn(parsed_input, context)
    return result


async def _handle_auto_mode(
    tool: Any,
    input_data: dict,
    context: Any,
    result: PermissionDecision,
    tool_use_id: str,
    assistant_message: Any,
) -> PermissionDecision:
    """Handles auto mode permission checking via the YOLO classifier."""
    from optimus.utils.permissions.yolo_classifier import classify_yolo_action, format_action_for_classifier

    app_state = context.get_app_state()
    tool_permission_context = app_state.tool_permission_context
    signal = getattr(context, "abort_controller", None)
    if signal is not None:
        signal = getattr(signal, "signal", None)

    action = format_action_for_classifier(tool.name, input_data)

    try:
        classifier_result = await classify_yolo_action(
            context.messages,
            action,
            getattr(context, "options", {}).get("tools", []) if hasattr(context, "options") else [],
            tool_permission_context,
            signal,
        )
    except Exception:
        # On classifier failure, fall back to prompting
        return result

    if classifier_result.unavailable:
        return result  # Fall back to prompting

    if classifier_result.should_block:
        return PermissionDenyDecision(
            message=f"Auto mode classifier blocked this action: {classifier_result.reason}",
            decision_reason={"type": "mode", "mode": "auto"},
        )

    return PermissionAllowDecision(
        updated_input=input_data,
        decision_reason={"type": "mode", "mode": "auto"},
    )


def _try_record_success(context: Any) -> None:
    """Records a successful tool use in denial tracking state."""
    try:
        from optimus.utils.permissions.denial_tracking import record_success

        app_state = context.get_app_state()
        denial_state = getattr(app_state, "denial_tracking", None)
        if denial_state and denial_state.consecutive_denials > 0:
            new_state = record_success(denial_state)
            context.set_app_state(lambda prev: type(prev)(**{**vars(prev), "denial_tracking": new_state}))
    except Exception:
        pass


async def _run_permission_request_hooks_headless(
    tool: Any,
    input_data: dict,
    tool_use_id: str,
    context: Any,
) -> PermissionDecision | None:
    """Runs PermissionRequest hooks for headless agents."""
    try:
        from optimus.utils.hooks import execute_permission_request_hooks
        from optimus.utils.permissions.permission_update import apply_permission_updates, persist_permission_updates

        app_state = context.get_app_state()
        signal = getattr(getattr(context, "abort_controller", None), "signal", None)

        async for hook_result in execute_permission_request_hooks(
            tool.name,
            tool_use_id,
            input_data,
            context,
            app_state.tool_permission_context.mode,
            None,
            signal,
        ):
            decision = getattr(hook_result, "permission_request_result", None)
            if not decision:
                continue
            if decision.behavior == "allow":
                updated_input = getattr(decision, "updated_input", None) or input_data
                updated_permissions = getattr(decision, "updated_permissions", None)
                if updated_permissions:
                    persist_permission_updates(updated_permissions)
                    context.set_app_state(
                        lambda prev: type(prev)(**{
                            **vars(prev),
                            "tool_permission_context": apply_permission_updates(
                                prev.tool_permission_context, updated_permissions
                            ),
                        })
                    )
                return PermissionAllowDecision(
                    updated_input=updated_input,
                    decision_reason={"type": "hook", "hookName": "PermissionRequest"},
                )
            if decision.behavior == "deny":
                if getattr(decision, "interrupt", False):
                    if hasattr(context, "abort_controller"):
                        context.abort_controller.abort()
                return PermissionDenyDecision(
                    message=getattr(decision, "message", "Permission denied by hook"),
                    decision_reason={
                        "type": "hook",
                        "hookName": "PermissionRequest",
                        "reason": getattr(decision, "message", None),
                    },
                )
    except Exception:
        pass
    return None
