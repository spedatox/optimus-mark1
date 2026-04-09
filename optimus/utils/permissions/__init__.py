"""
optimus.utils.permissions
=========================

Python port of src/utils/permissions/.

Public surface mirrors what permissions.ts (and its re-exports) expose.
All symbols are importable from this package directly, e.g.:

    from optimus.utils.permissions import check_permission, get_allow_rules
"""
from __future__ import annotations

# --- Permission Mode ---------------------------------------------------------
from optimus.utils.permissions.permission_mode import (
    EXTERNAL_PERMISSION_MODES,
    PERMISSION_MODES,
    ExternalPermissionMode,
    ModeColorKey,
    PermissionMode,
    get_mode_color,
    is_default_mode,
    is_external_permission_mode,
    permission_mode_from_string,
    permission_mode_short_title,
    permission_mode_symbol,
    permission_mode_title,
    to_external_permission_mode,
)

# --- Permission Result --------------------------------------------------------
from optimus.utils.permissions.permission_result import (
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionDecision,
    PermissionDecisionReason,
    PermissionDenyDecision,
    PermissionMetadata,
    PermissionResult,
    get_rule_behavior_description,
)

# --- Permission Rule ----------------------------------------------------------
from optimus.utils.permissions.permission_rule import (
    PermissionBehavior,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
)

# --- Permission Update Schema -------------------------------------------------
from optimus.utils.permissions.permission_update_schema import (
    AddDirectoriesUpdate,
    AddRulesUpdate,
    AnyPermissionUpdate,
    PermissionUpdateDestination,
    PermissionUpdateModel,
    RemoveDirectoriesUpdate,
    RemoveRulesUpdate,
    ReplaceRulesUpdate,
    SetModeUpdate,
)

# --- Permission Update (apply / persist) --------------------------------------
from optimus.utils.permissions.permission_update import (
    apply_permission_update,
    apply_permission_updates,
    create_read_rule_suggestion,
    extract_rules,
    has_rules,
    persist_permission_update,
    persist_permission_updates,
    supports_persistence,
)

# --- Permission Rule Parser ---------------------------------------------------
from optimus.utils.permissions.permission_rule_parser import (
    escape_rule_content,
    get_legacy_tool_names,
    normalize_legacy_tool_name,
    permission_rule_value_from_string,
    permission_rule_value_to_string,
    unescape_rule_content,
)

# --- Core Permissions --------------------------------------------------------
from optimus.utils.permissions.permissions import (
    apply_permission_rules_to_permission_context,
    create_permission_request_message,
    filter_denied_agents,
    get_allow_rules,
    get_ask_rule_for_tool,
    get_ask_rules,
    get_deny_rule_for_agent,
    get_deny_rule_for_tool,
    get_deny_rules,
    get_rule_by_contents_for_tool,
    get_rule_by_contents_for_tool_name,
    has_permissions_to_use_tool,
    permission_rule_source_display_string,
    tool_always_allowed_rule,
)

# --- Permission Setup --------------------------------------------------------
from optimus.utils.permissions.permission_setup import (
    DangerousPermissionInfo,
    create_disabled_bypass_permissions_context,
    find_dangerous_classifier_permissions,
    find_overly_broad_bash_permissions,
    find_overly_broad_power_shell_permissions,
    get_auto_mode_unavailable_reason,
    initial_permission_mode_from_cli,
    is_auto_mode_gate_enabled,
    is_dangerous_bash_permission,
    is_dangerous_power_shell_permission,
    is_dangerous_task_permission,
    is_overly_broad_bash_allow_rule,
    is_overly_broad_power_shell_allow_rule,
    remove_dangerous_permissions,
    restore_dangerous_permissions,
    should_disable_bypass_permissions,
    strip_dangerous_permissions_for_auto_mode,
    transition_permission_mode,
    verify_auto_mode_gate_access,
)

# --- Permissions Loader -------------------------------------------------------
from optimus.utils.permissions.permissions_loader import (
    PermissionRuleFromEditableSettings,
    add_permission_rules_to_settings,
    delete_permission_rule_from_settings,
    get_permission_rules_for_source,
    load_all_permission_rules_from_disk,
    should_allow_managed_permission_rules_only,
    should_show_always_allow_options,
)

# --- Path Validation ----------------------------------------------------------
from optimus.utils.permissions.path_validation import (
    FileOperationType,
    PathCheckResult,
    ResolvedPathCheckResult,
    expand_tilde,
    format_directory_list,
    get_glob_base_directory,
    is_dangerous_removal_path,
    is_path_allowed,
    is_path_in_sandbox_write_allowlist,
    validate_glob_pattern,
    validate_path,
)

# --- Filesystem ---------------------------------------------------------------
from optimus.utils.permissions.filesystem import (
    DANGEROUS_DIRECTORIES,
    DANGEROUS_FILES,
    all_working_directories,
    check_editable_internal_path,
    check_path_safety_for_auto_edit,
    check_read_permission_for_tool,
    check_readable_internal_path,
    get_claude_temp_dir,
    get_claude_temp_dir_name,
    get_file_read_ignore_patterns,
    get_project_temp_dir,
    get_scratchpad_dir,
    get_session_memory_dir,
    get_session_memory_path,
    is_claude_settings_path,
    is_scratchpad_enabled,
    matching_rule_for_input,
    normalize_case_for_comparison,
    normalize_patterns_to_path,
    path_in_allowed_working_path,
    path_in_working_path,
    relative_path,
    to_posix_path,
)

# --- Dangerous Patterns -------------------------------------------------------
from optimus.utils.permissions.dangerous_patterns import (
    CROSS_PLATFORM_CODE_EXEC,
    DANGEROUS_BASH_PATTERNS,
)

# --- Shell Rule Matching ------------------------------------------------------
from optimus.utils.permissions.shell_rule_matching import (
    ExactRule,
    PrefixRule,
    ShellPermissionRule,
    WildcardRule,
    has_wildcards,
    match_wildcard_pattern,
    parse_permission_rule,
    permission_rule_extract_prefix,
    suggestion_for_exact_command,
    suggestion_for_prefix,
)

# --- Classifier Shared --------------------------------------------------------
from optimus.utils.permissions.classifier_shared import (
    extract_tool_use_block,
    parse_classifier_response,
)

# --- Classifier Decision (auto mode allowlist) --------------------------------
from optimus.utils.permissions.classifier_decision import (
    SAFE_YOLO_ALLOWLISTED_TOOLS,
    is_auto_mode_allowlisted_tool,
)

# --- Bash Classifier (stub) ---------------------------------------------------
from optimus.utils.permissions.bash_classifier import (
    PROMPT_PREFIX,
    classify_bash_command,
    create_prompt_rule_content,
    extract_prompt_description,
    generate_generic_description,
    get_bash_prompt_allow_descriptions,
    get_bash_prompt_ask_descriptions,
    get_bash_prompt_deny_descriptions,
    is_classifier_permissions_enabled,
)

# --- YOLO Classifier (stub) ---------------------------------------------------
from optimus.utils.permissions.yolo_classifier import (
    YOLO_CLASSIFIER_TOOL_NAME,
    AutoModeRules,
    classify_yolo_action,
    format_action_for_classifier,
    get_default_external_auto_mode_rules,
)

# --- Auto Mode State ----------------------------------------------------------
from optimus.utils.permissions.auto_mode_state import (
    get_auto_mode_flag_cli,
    is_auto_mode_active,
    is_auto_mode_circuit_broken,
    reset_for_testing,
    set_auto_mode_active,
    set_auto_mode_circuit_broken,
    set_auto_mode_flag_cli,
)

# --- Bypass Permissions Killswitch -------------------------------------------
from optimus.utils.permissions.bypass_permissions_killswitch import (
    check_and_disable_auto_mode_if_needed,
    check_and_disable_bypass_permissions_if_needed,
    reset_auto_mode_gate_check,
    reset_bypass_permissions_check,
)

# --- Denial Tracking ----------------------------------------------------------
from optimus.utils.permissions.denial_tracking import (
    DENIAL_LIMITS,
    DenialTrackingState,
    create_denial_tracking_state,
    record_denial,
    record_success,
    should_fallback_to_prompting,
)

# --- Next Permission Mode -----------------------------------------------------
from optimus.utils.permissions.get_next_permission_mode import (
    cycle_permission_mode,
    get_next_permission_mode,
)

# --- Shadowed Rule Detection --------------------------------------------------
from optimus.utils.permissions.shadowed_rule_detection import (
    DetectUnreachableRulesOptions,
    ShadowType,
    UnreachableRule,
    detect_unreachable_rules,
    is_shared_setting_source,
)

# --- Permission Explainer -----------------------------------------------------
from optimus.utils.permissions.permission_explainer import (
    generate_permission_explanation,
    is_permission_explainer_enabled,
)

# --- Permission Prompt Tool Result Schema ------------------------------------
from optimus.utils.permissions.permission_prompt_tool_result_schema import (
    PermissionAllowResult,
    PermissionDenyResult,
    PermissionPromptInput,
    PermissionPromptOutput,
    permission_prompt_tool_result_to_permission_decision,
)

__all__ = [
    # Permission Mode
    "EXTERNAL_PERMISSION_MODES",
    "PERMISSION_MODES",
    "ExternalPermissionMode",
    "ModeColorKey",
    "PermissionMode",
    "get_mode_color",
    "is_default_mode",
    "is_external_permission_mode",
    "permission_mode_from_string",
    "permission_mode_short_title",
    "permission_mode_symbol",
    "permission_mode_title",
    "to_external_permission_mode",
    # Permission Result
    "PermissionAllowDecision",
    "PermissionAskDecision",
    "PermissionDecision",
    "PermissionDecisionReason",
    "PermissionDenyDecision",
    "PermissionMetadata",
    "PermissionResult",
    "get_rule_behavior_description",
    # Permission Rule
    "PermissionBehavior",
    "PermissionRule",
    "PermissionRuleSource",
    "PermissionRuleValue",
    # Permission Update Schema
    "AddDirectoriesUpdate",
    "AddRulesUpdate",
    "AnyPermissionUpdate",
    "PermissionUpdateDestination",
    "PermissionUpdateModel",
    "RemoveDirectoriesUpdate",
    "RemoveRulesUpdate",
    "ReplaceRulesUpdate",
    "SetModeUpdate",
    # Permission Update
    "apply_permission_update",
    "apply_permission_updates",
    "create_read_rule_suggestion",
    "extract_rules",
    "has_rules",
    "persist_permission_update",
    "persist_permission_updates",
    "supports_persistence",
    # Permission Rule Parser
    "escape_rule_content",
    "get_legacy_tool_names",
    "normalize_legacy_tool_name",
    "permission_rule_value_from_string",
    "permission_rule_value_to_string",
    "unescape_rule_content",
    # Core Permissions
    "apply_permission_rules_to_permission_context",
    "create_permission_request_message",
    "filter_denied_agents",
    "get_allow_rules",
    "get_ask_rule_for_tool",
    "get_ask_rules",
    "get_deny_rule_for_agent",
    "get_deny_rule_for_tool",
    "get_deny_rules",
    "get_rule_by_contents_for_tool",
    "get_rule_by_contents_for_tool_name",
    "has_permissions_to_use_tool",
    "permission_rule_source_display_string",
    "tool_always_allowed_rule",
    # Permission Setup
    "DangerousPermissionInfo",
    "create_disabled_bypass_permissions_context",
    "find_dangerous_classifier_permissions",
    "find_overly_broad_bash_permissions",
    "find_overly_broad_power_shell_permissions",
    "get_auto_mode_unavailable_reason",
    "initial_permission_mode_from_cli",
    "is_auto_mode_gate_enabled",
    "is_dangerous_bash_permission",
    "is_dangerous_power_shell_permission",
    "is_dangerous_task_permission",
    "is_overly_broad_bash_allow_rule",
    "is_overly_broad_power_shell_allow_rule",
    "remove_dangerous_permissions",
    "restore_dangerous_permissions",
    "should_disable_bypass_permissions",
    "strip_dangerous_permissions_for_auto_mode",
    "transition_permission_mode",
    "verify_auto_mode_gate_access",
    # Permissions Loader
    "PermissionRuleFromEditableSettings",
    "add_permission_rules_to_settings",
    "delete_permission_rule_from_settings",
    "get_permission_rules_for_source",
    "load_all_permission_rules_from_disk",
    "should_allow_managed_permission_rules_only",
    "should_show_always_allow_options",
    # Path Validation
    "FileOperationType",
    "PathCheckResult",
    "ResolvedPathCheckResult",
    "expand_tilde",
    "format_directory_list",
    "get_glob_base_directory",
    "is_dangerous_removal_path",
    "is_path_allowed",
    "is_path_in_sandbox_write_allowlist",
    "validate_glob_pattern",
    "validate_path",
    # Filesystem
    "DANGEROUS_DIRECTORIES",
    "DANGEROUS_FILES",
    "all_working_directories",
    "check_editable_internal_path",
    "check_path_safety_for_auto_edit",
    "check_read_permission_for_tool",
    "check_readable_internal_path",
    "get_claude_temp_dir",
    "get_claude_temp_dir_name",
    "get_file_read_ignore_patterns",
    "get_project_temp_dir",
    "get_scratchpad_dir",
    "get_session_memory_dir",
    "get_session_memory_path",
    "is_claude_settings_path",
    "is_scratchpad_enabled",
    "matching_rule_for_input",
    "normalize_case_for_comparison",
    "normalize_patterns_to_path",
    "path_in_allowed_working_path",
    "path_in_working_path",
    "relative_path",
    "to_posix_path",
    # Dangerous Patterns
    "CROSS_PLATFORM_CODE_EXEC",
    "DANGEROUS_BASH_PATTERNS",
    # Shell Rule Matching
    "ExactRule",
    "PrefixRule",
    "ShellPermissionRule",
    "WildcardRule",
    "has_wildcards",
    "match_wildcard_pattern",
    "parse_permission_rule",
    "permission_rule_extract_prefix",
    "suggestion_for_exact_command",
    "suggestion_for_prefix",
    # Classifier Shared
    "extract_tool_use_block",
    "parse_classifier_response",
    # Classifier Decision
    "SAFE_YOLO_ALLOWLISTED_TOOLS",
    "is_auto_mode_allowlisted_tool",
    # Bash Classifier
    "PROMPT_PREFIX",
    "classify_bash_command",
    "create_prompt_rule_content",
    "extract_prompt_description",
    "generate_generic_description",
    "get_bash_prompt_allow_descriptions",
    "get_bash_prompt_ask_descriptions",
    "get_bash_prompt_deny_descriptions",
    "is_classifier_permissions_enabled",
    # YOLO Classifier
    "YOLO_CLASSIFIER_TOOL_NAME",
    "AutoModeRules",
    "classify_yolo_action",
    "format_action_for_classifier",
    "get_default_external_auto_mode_rules",
    # Auto Mode State
    "get_auto_mode_flag_cli",
    "is_auto_mode_active",
    "is_auto_mode_circuit_broken",
    "reset_for_testing",
    "set_auto_mode_active",
    "set_auto_mode_circuit_broken",
    "set_auto_mode_flag_cli",
    # Bypass Permissions Killswitch
    "check_and_disable_auto_mode_if_needed",
    "check_and_disable_bypass_permissions_if_needed",
    "reset_auto_mode_gate_check",
    "reset_bypass_permissions_check",
    # Denial Tracking
    "DENIAL_LIMITS",
    "DenialTrackingState",
    "create_denial_tracking_state",
    "record_denial",
    "record_success",
    "should_fallback_to_prompting",
    # Next Permission Mode
    "cycle_permission_mode",
    "get_next_permission_mode",
    # Shadowed Rule Detection
    "DetectUnreachableRulesOptions",
    "ShadowType",
    "UnreachableRule",
    "detect_unreachable_rules",
    "is_shared_setting_source",
    # Permission Explainer
    "generate_permission_explanation",
    "is_permission_explainer_enabled",
    # Permission Prompt Tool Result Schema
    "PermissionAllowResult",
    "PermissionDenyResult",
    "PermissionPromptInput",
    "PermissionPromptOutput",
    "permission_prompt_tool_result_to_permission_decision",
]
