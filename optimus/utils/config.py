"""
Configuration system — global and per-project config read/write with locking.
Mirrors src/utils/config.ts

The entire application reads from a single ~/.claude.json file.
  - Global settings live at the top level.
  - Per-project settings live under config.projects[<project_path>].

Key design decisions:
  - Cache: One in-memory cache with mtime-based invalidation (no lock needed for reads).
  - Lock: fcntl/msvcrt file lock on writes to prevent concurrent-process races.
  - Auth-loss guard: Never overwrite cached auth data with defaults (GH #3117).
  - Backups: Timestamped backups in ~/.claude/backups/ before every write.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid as _uuid_mod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal

# ---------------------------------------------------------------------------
# Forward-declared / optional imports (loaded lazily to break cycles)
# ---------------------------------------------------------------------------

def _get_claude_config_home_dir() -> str:
    from optimus.utils.env_utils import get_claude_config_home_dir
    return get_claude_config_home_dir()


def _get_global_claude_file() -> str:
    from optimus.utils.env import get_global_claude_file
    return get_global_claude_file()


def _get_original_cwd() -> str:
    try:
        from optimus.bootstrap.state import get_original_cwd
        return get_original_cwd()
    except ImportError:
        return os.getcwd()


def _get_session_trust_accepted() -> bool:
    try:
        from optimus.bootstrap.state import get_session_trust_accepted
        return get_session_trust_accepted()
    except ImportError:
        return False


def _find_canonical_git_root(path: str) -> str | None:
    try:
        from optimus.utils.git import find_canonical_git_root
        return find_canonical_git_root(path)
    except ImportError:
        return None


def _normalize_path_for_config_key(path: str) -> str:
    try:
        from optimus.utils.path import normalize_path_for_config_key
        return normalize_path_for_config_key(path)
    except ImportError:
        return path.replace("\\", "/")


def _get_cwd() -> str:
    try:
        from optimus.utils.cwd import get_cwd
        return get_cwd()
    except ImportError:
        return os.getcwd()


def _is_env_truthy(val: str | None) -> bool:
    try:
        from optimus.utils.env_utils import is_env_truthy
        return is_env_truthy(val)
    except ImportError:
        return val is not None and val.lower() in ("1", "true", "yes")


def _get_essential_traffic_only_reason() -> str | None:
    try:
        from optimus.utils.privacy_level import get_essential_traffic_only_reason
        return get_essential_traffic_only_reason()
    except ImportError:
        return None


def _feature(name: str) -> bool:
    try:
        from optimus.utils.features import feature
        return feature(name)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------

ReleaseChannel = Literal["stable", "latest"]
InstallMethod = Literal["local", "native", "global", "unknown"]
EditorMode = Literal["emacs", "vim", "vscode", "normal"]
DiffTool = Literal["terminal", "auto"]
OutputStyle = str
NotificationChannel = str  # type alias, resolved via configConstants
ThemeSetting = str         # type alias, resolved via theme module


# ---------------------------------------------------------------------------
# PastedContent
# ---------------------------------------------------------------------------


@dataclass
class ImageDimensions:
    width: int
    height: int
    original_width: int | None = None
    original_height: int | None = None


@dataclass
class PastedContent:
    id: int
    type: Literal["text", "image"]
    content: str
    media_type: str | None = None     # e.g. 'image/png'
    filename: str | None = None
    dimensions: ImageDimensions | None = None
    source_path: str | None = None


@dataclass
class SerializedStructuredHistoryEntry:
    display: str
    pasted_contents: dict[int, PastedContent] | None = None
    pasted_text: str | None = None


@dataclass
class HistoryEntry:
    display: str
    pasted_contents: dict[int, PastedContent] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AccountInfo
# ---------------------------------------------------------------------------


@dataclass
class AccountInfo:
    account_uuid: str
    email_address: str
    organization_uuid: str | None = None
    organization_name: str | None = None
    organization_role: str | None = None
    workspace_role: str | None = None
    display_name: str | None = None
    has_extra_usage_enabled: bool | None = None
    billing_type: str | None = None   # BillingType from oauth types
    account_created_at: str | None = None
    subscription_created_at: str | None = None


# ---------------------------------------------------------------------------
# ProjectConfig
# ---------------------------------------------------------------------------


@dataclass
class ActiveWorktreeSession:
    original_cwd: str
    worktree_path: str
    worktree_name: str
    session_id: str
    original_branch: str | None = None
    hook_based: bool | None = None


@dataclass
class ProjectConfig:
    allowed_tools: list[str] = field(default_factory=list)
    mcp_context_uris: list[str] = field(default_factory=list)
    mcp_servers: dict[str, Any] | None = field(default_factory=dict)  # McpServerConfig
    last_api_duration: float | None = None
    last_api_duration_without_retries: float | None = None
    last_tool_duration: float | None = None
    last_cost: float | None = None
    last_duration: float | None = None
    last_lines_added: int | None = None
    last_lines_removed: int | None = None
    last_total_input_tokens: int | None = None
    last_total_output_tokens: int | None = None
    last_total_cache_creation_input_tokens: int | None = None
    last_total_cache_read_input_tokens: int | None = None
    last_total_web_search_requests: int | None = None
    last_fps_average: float | None = None
    last_fps_low1_pct: float | None = None
    last_session_id: str | None = None
    last_model_usage: dict[str, dict[str, Any]] | None = None
    last_session_metrics: dict[str, float] | None = None
    example_files: list[str] | None = None
    example_files_generated_at: float | None = None
    has_trust_dialog_accepted: bool | None = False
    has_completed_project_onboarding: bool | None = None
    project_onboarding_seen_count: int = 0
    has_claude_md_external_includes_approved: bool | None = False
    has_claude_md_external_includes_warning_shown: bool | None = False
    enabled_mcpjson_servers: list[str] | None = field(default_factory=list)
    disabled_mcpjson_servers: list[str] | None = field(default_factory=list)
    enable_all_project_mcp_servers: bool | None = None
    disabled_mcp_servers: list[str] | None = None
    enabled_mcp_servers: list[str] | None = None
    active_worktree_session: ActiveWorktreeSession | None = None
    remote_control_spawn_mode: Literal["same-dir", "worktree"] | None = None


DEFAULT_PROJECT_CONFIG = ProjectConfig(
    allowed_tools=[],
    mcp_context_uris=[],
    mcp_servers={},
    enabled_mcpjson_servers=[],
    disabled_mcpjson_servers=[],
    has_trust_dialog_accepted=False,
    project_onboarding_seen_count=0,
    has_claude_md_external_includes_approved=False,
    has_claude_md_external_includes_warning_shown=False,
)


# ---------------------------------------------------------------------------
# GlobalConfig
# ---------------------------------------------------------------------------


@dataclass
class GlobalConfig:
    # Required fields (with defaults)
    num_startups: int = 0
    theme: str = "dark"
    preferred_notif_channel: str = "auto"
    verbose: bool = False
    auto_compact_enabled: bool = True
    show_turn_duration: bool = True
    env: dict[str, str] = field(default_factory=dict)
    tips_history: dict[str, int] = field(default_factory=dict)
    memory_usage_count: int = 0
    prompt_queue_use_count: int = 0
    btw_use_count: int = 0
    todo_feature_enabled: bool = True
    message_idle_notif_threshold_ms: int = 60000
    file_checkpointing_enabled: bool = True
    terminal_progress_bar_enabled: bool = True
    cached_statsig_gates: dict[str, bool] = field(default_factory=dict)
    respect_gitignore: bool = True
    copy_full_response: bool = False

    # Optional fields
    api_key_helper: str | None = None
    projects: dict[str, Any] | None = None  # dict[str, ProjectConfig]
    install_method: InstallMethod | None = None
    auto_updates: bool | None = None
    auto_updates_protected_for_native: bool | None = None
    doctor_shown_at_session: int | None = None
    user_id: str | None = None
    has_completed_onboarding: bool | None = None
    last_onboarding_version: str | None = None
    last_release_notes_seen: str | None = None
    changelog_last_fetched: float | None = None
    cached_changelog: str | None = None
    mcp_servers: dict[str, Any] | None = None
    claude_ai_mcp_ever_connected: list[str] | None = None
    custom_notify_command: str | None = None
    custom_api_key_responses: dict[str, list[str]] | None = None
    primary_api_key: str | None = None
    has_acknowledged_cost_threshold: bool | None = None
    has_seen_undercover_auto_notice: bool | None = None
    has_seen_ultraplan_terms: bool | None = None
    has_reset_auto_mode_opt_in_for_default_offer: bool | None = None
    oauth_account: AccountInfo | dict[str, Any] | None = None
    iterm2_key_binding_installed: bool | None = None
    editor_mode: EditorMode | None = None
    bypass_permissions_mode_accepted: bool | None = None
    has_used_backslash_return: bool | None = None
    has_seen_tasks_hint: bool | None = False
    has_used_stash: bool | None = False
    has_used_background_task: bool | None = False
    queued_command_up_hint_count: int | None = 0
    diff_tool: DiffTool | None = "auto"
    iterm2_setup_in_progress: bool | None = None
    iterm2_backup_path: str | None = None
    apple_terminal_backup_path: str | None = None
    apple_terminal_setup_in_progress: bool | None = None
    shift_enter_key_binding_installed: bool | None = None
    option_as_meta_key_installed: bool | None = None
    auto_connect_ide: bool | None = False
    auto_install_ide_extension: bool | None = True
    has_ide_onboarding_been_shown: dict[str, bool] | None = None
    ide_hint_shown_count: int | None = None
    has_ide_auto_connect_dialog_been_shown: bool | None = None
    companion: dict[str, Any] | None = None
    companion_muted: bool | None = None
    feedback_survey_state: dict[str, Any] | None = None
    transcript_share_dismissed: bool | None = None
    has_shown_s1m_welcome_v2: dict[str, bool] | None = None
    s1m_access_cache: dict[str, Any] | None = None
    s1m_non_subscriber_access_cache: dict[str, Any] | None = None
    passes_eligibility_cache: dict[str, Any] | None = None
    grove_config_cache: dict[str, Any] | None = None
    passes_upsell_seen_count: int | None = None
    has_visited_passes: bool | None = None
    passes_last_seen_remaining: int | None = None
    overage_credit_grant_cache: dict[str, Any] | None = None
    overage_credit_upsell_seen_count: int | None = None
    has_visited_extra_usage: bool | None = None
    voice_notice_seen_count: int | None = None
    voice_lang_hint_shown_count: int | None = None
    voice_lang_hint_last_language: str | None = None
    voice_footer_hint_seen_count: int | None = None
    opus1m_merge_notice_seen_count: int | None = None
    experiment_notices_seen_count: dict[str, int] | None = None
    has_shown_opus_plan_welcome: dict[str, bool] | None = None
    last_plan_mode_use: float | None = None
    subscription_notice_count: int | None = None
    has_available_subscription: bool | None = None
    subscription_upsell_shown_count: int | None = None
    recommended_subscription: str | None = None
    show_expanded_todos: bool | None = False
    show_spinner_tree: bool | None = None
    first_start_time: str | None = None
    github_action_setup_count: int | None = None
    slack_app_install_count: int | None = None
    show_status_in_terminal_tab: bool | None = None
    task_complete_notif_enabled: bool | None = None
    input_needed_notif_enabled: bool | None = None
    agent_push_notif_enabled: bool | None = None
    claude_code_first_token_date: str | None = None
    model_switch_callout_dismissed: bool | None = None
    model_switch_callout_last_shown: float | None = None
    model_switch_callout_version: str | None = None
    effort_callout_dismissed: bool | None = None
    effort_callout_v2_dismissed: bool | None = None
    remote_dialog_seen: bool | None = None
    bridge_oauth_dead_expires_at: float | None = None
    bridge_oauth_dead_fail_count: int | None = None
    desktop_upsell_seen_count: int | None = None
    desktop_upsell_dismissed: bool | None = None
    idle_return_dismissed: bool | None = None
    opus_pro_migration_complete: bool | None = None
    opus_pro_migration_timestamp: float | None = None
    sonnet1m45_migration_complete: bool | None = None
    legacy_opus_migration_timestamp: float | None = None
    sonnet45_to46_migration_timestamp: float | None = None
    cached_dynamic_configs: dict[str, Any] | None = field(default_factory=dict)
    cached_growth_book_features: dict[str, Any] | None = field(default_factory=dict)
    growth_book_overrides: dict[str, Any] | None = None
    last_shown_emergency_tip: str | None = None
    copy_on_select: bool | None = None
    github_repo_paths: dict[str, list[str]] | None = None
    deep_link_terminal: str | None = None
    iterm2_it2_setup_complete: bool | None = None
    prefer_tmux_over_iterm2: bool | None = None
    skill_usage: dict[str, Any] | None = None
    official_marketplace_auto_install_attempted: bool | None = None
    official_marketplace_auto_installed: bool | None = None
    official_marketplace_auto_install_fail_reason: str | None = None
    official_marketplace_auto_install_retry_count: int | None = None
    official_marketplace_auto_install_last_attempt_time: float | None = None
    official_marketplace_auto_install_next_retry_time: float | None = None
    has_completed_claude_in_chrome_onboarding: bool | None = None
    claude_in_chrome_default_enabled: bool | None = None
    cached_chrome_extension_installed: bool | None = None
    chrome_extension: dict[str, Any] | None = None
    lsp_recommendation_disabled: bool | None = None
    lsp_recommendation_never_plugins: list[str] | None = None
    lsp_recommendation_ignored_count: int | None = None
    claude_code_hints: dict[str, Any] | None = None
    permission_explainer_enabled: bool | None = None
    teammate_mode: Literal["auto", "tmux", "in-process"] | None = None
    teammate_default_model: str | None = None
    pr_status_footer_enabled: bool | None = None
    tungsten_panel_visible: bool | None = None
    penguin_mode_org_enabled: bool | None = None
    startup_prefetched_at: float | None = None
    remote_control_at_startup: bool | None = None
    cached_extra_usage_disabled_reason: str | None = None
    auto_permissions_notification_count: int | None = None
    speculation_enabled: bool | None = None
    client_data_cache: dict[str, Any] | None = None
    additional_model_options_cache: list[dict[str, Any]] | None = None
    metrics_status_cache: dict[str, Any] | None = None
    migration_version: int | None = None


def create_default_global_config() -> GlobalConfig:
    """Factory: returns a fresh GlobalConfig with safe defaults (no shared mutable state)."""
    return GlobalConfig(
        num_startups=0,
        install_method=None,
        auto_updates=None,
        theme="dark",
        preferred_notif_channel="auto",
        verbose=False,
        editor_mode=None,
        auto_compact_enabled=True,
        show_turn_duration=True,
        has_seen_tasks_hint=False,
        has_used_stash=False,
        has_used_background_task=False,
        queued_command_up_hint_count=0,
        diff_tool="auto",
        custom_api_key_responses={"approved": [], "rejected": []},
        env={},
        tips_history={},
        memory_usage_count=0,
        prompt_queue_use_count=0,
        btw_use_count=0,
        todo_feature_enabled=True,
        show_expanded_todos=False,
        message_idle_notif_threshold_ms=60000,
        auto_connect_ide=False,
        auto_install_ide_extension=True,
        file_checkpointing_enabled=True,
        terminal_progress_bar_enabled=True,
        cached_statsig_gates={},
        cached_dynamic_configs={},
        cached_growth_book_features={},
        respect_gitignore=True,
        copy_full_response=False,
    )


DEFAULT_GLOBAL_CONFIG: GlobalConfig = create_default_global_config()

# Keys that are user-facing (surfaced via /config)
GLOBAL_CONFIG_KEYS: tuple[str, ...] = (
    "apiKeyHelper",
    "installMethod",
    "autoUpdates",
    "autoUpdatesProtectedForNative",
    "theme",
    "verbose",
    "preferredNotifChannel",
    "shiftEnterKeyBindingInstalled",
    "editorMode",
    "hasUsedBackslashReturn",
    "autoCompactEnabled",
    "showTurnDuration",
    "diffTool",
    "env",
    "tipsHistory",
    "todoFeatureEnabled",
    "showExpandedTodos",
    "messageIdleNotifThresholdMs",
    "autoConnectIde",
    "autoInstallIdeExtension",
    "fileCheckpointingEnabled",
    "terminalProgressBarEnabled",
    "showStatusInTerminalTab",
    "taskCompleteNotifEnabled",
    "inputNeededNotifEnabled",
    "agentPushNotifEnabled",
    "respectGitignore",
    "claudeInChromeDefaultEnabled",
    "hasCompletedClaudeInChromeOnboarding",
    "lspRecommendationDisabled",
    "lspRecommendationNeverPlugins",
    "lspRecommendationIgnoredCount",
    "copyFullResponse",
    "copyOnSelect",
    "permissionExplainerEnabled",
    "prStatusFooterEnabled",
    "remoteControlAtStartup",
    "remoteDialogSeen",
)

GlobalConfigKey = str  # type alias

PROJECT_CONFIG_KEYS: tuple[str, ...] = (
    "allowedTools",
    "hasTrustDialogAccepted",
    "hasCompletedProjectOnboarding",
)

ProjectConfigKey = str  # type alias


def is_global_config_key(key: str) -> bool:
    return key in GLOBAL_CONFIG_KEYS


def is_project_config_key(key: str) -> bool:
    return key in PROJECT_CONFIG_KEYS


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _strip_bom(text: str) -> str:
    """Strip UTF-8 BOM if present (added by PowerShell 5.x)."""
    return text.lstrip("\ufeff")


def _json_loads(text: str) -> Any:
    return json.loads(text)


def _json_dumps(obj: Any, indent: int | None = None) -> str:
    return json.dumps(obj, indent=indent, ensure_ascii=False)


def _to_json_serializable(obj: Any) -> Any:
    """Convert dataclasses / known types to plain dicts for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_serializable(i) for i in obj]
    # dataclass support
    try:
        import dataclasses
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: _to_json_serializable(v) for k, v in dataclasses.asdict(obj).items()}
    except Exception:
        pass
    return obj


# ---------------------------------------------------------------------------
# File locking (cross-platform)
# ---------------------------------------------------------------------------

_write_lock = Lock()  # In-process lock (guards against thread races)


def _acquire_file_lock(lock_path: str) -> Any:
    """
    Acquire an exclusive advisory file lock. Returns a context manager / release callable.
    Uses fcntl on POSIX, msvcrt on Windows.
    """
    lock_file = open(lock_path, "w")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX)
    except Exception:
        lock_file.close()
        raise
    return lock_file


def _release_file_lock(lock_file: Any) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    finally:
        lock_file.close()


# ---------------------------------------------------------------------------
# Config read / write internals
# ---------------------------------------------------------------------------

# Re-entrancy guard: prevents getConfig → logEvent → getGlobalConfig → getConfig
_inside_get_config = False

# Flag: raised by enable_configs() before any read is allowed
_config_reading_allowed = os.environ.get("NODE_ENV") == "test"


def enable_configs() -> None:
    """Allow config reads. Must be called once before getGlobalConfig()."""
    global _config_reading_allowed
    if _config_reading_allowed:
        return
    _config_reading_allowed = True
    _get_config_from_file(
        _get_global_claude_file(),
        create_default_global_config,
        throw_on_invalid=True,
    )


class ConfigParseError(Exception):
    def __init__(self, message: str, file: str, default: Any) -> None:
        super().__init__(message)
        self.file = file
        self.default = default


def _get_config_backup_dir() -> str:
    return str(Path(_get_claude_config_home_dir()) / "backups")


def _find_most_recent_backup(file: str) -> str | None:
    file_base = Path(file).name
    backup_dir = Path(_get_config_backup_dir())

    # New backup dir
    try:
        backups = sorted(
            f for f in backup_dir.iterdir() if f.name.startswith(f"{file_base}.backup.")
        )
        if backups:
            return str(backups[-1])
    except (FileNotFoundError, OSError):
        pass

    # Legacy: next to the config file
    file_dir = Path(file).parent
    try:
        backups = sorted(
            f for f in file_dir.iterdir() if f.name.startswith(f"{file_base}.backup.")
        )
        if backups:
            return str(backups[-1])
        legacy = Path(f"{file}.backup")
        if legacy.exists():
            return str(legacy)
    except (FileNotFoundError, OSError):
        pass

    return None


def _global_config_dict_to_obj(d: dict[str, Any]) -> GlobalConfig:
    """Merge raw dict over defaults and return a GlobalConfig dataclass."""
    defaults = create_default_global_config()
    # Map camelCase JSON keys to snake_case Python fields
    _CAMEL_TO_SNAKE: dict[str, str] = {
        "numStartups": "num_startups",
        "installMethod": "install_method",
        "autoUpdates": "auto_updates",
        "autoUpdatesProtectedForNative": "auto_updates_protected_for_native",
        "doctorShownAtSession": "doctor_shown_at_session",
        "userID": "user_id",
        "theme": "theme",
        "hasCompletedOnboarding": "has_completed_onboarding",
        "lastOnboardingVersion": "last_onboarding_version",
        "lastReleaseNotesSeen": "last_release_notes_seen",
        "changelogLastFetched": "changelog_last_fetched",
        "cachedChangelog": "cached_changelog",
        "mcpServers": "mcp_servers",
        "claudeAiMcpEverConnected": "claude_ai_mcp_ever_connected",
        "preferredNotifChannel": "preferred_notif_channel",
        "customNotifyCommand": "custom_notify_command",
        "verbose": "verbose",
        "customApiKeyResponses": "custom_api_key_responses",
        "primaryApiKey": "primary_api_key",
        "hasAcknowledgedCostThreshold": "has_acknowledged_cost_threshold",
        "hasSeenUndercoverAutoNotice": "has_seen_undercover_auto_notice",
        "hasSeenUltraplanTerms": "has_seen_ultraplan_terms",
        "hasResetAutoModeOptInForDefaultOffer": "has_reset_auto_mode_opt_in_for_default_offer",
        "oauthAccount": "oauth_account",
        "iterm2KeyBindingInstalled": "iterm2_key_binding_installed",
        "editorMode": "editor_mode",
        "bypassPermissionsModeAccepted": "bypass_permissions_mode_accepted",
        "hasUsedBackslashReturn": "has_used_backslash_return",
        "autoCompactEnabled": "auto_compact_enabled",
        "showTurnDuration": "show_turn_duration",
        "env": "env",
        "hasSeenTasksHint": "has_seen_tasks_hint",
        "hasUsedStash": "has_used_stash",
        "hasUsedBackgroundTask": "has_used_background_task",
        "queuedCommandUpHintCount": "queued_command_up_hint_count",
        "diffTool": "diff_tool",
        "iterm2SetupInProgress": "iterm2_setup_in_progress",
        "iterm2BackupPath": "iterm2_backup_path",
        "appleTerminalBackupPath": "apple_terminal_backup_path",
        "appleTerminalSetupInProgress": "apple_terminal_setup_in_progress",
        "shiftEnterKeyBindingInstalled": "shift_enter_key_binding_installed",
        "optionAsMetaKeyInstalled": "option_as_meta_key_installed",
        "autoConnectIde": "auto_connect_ide",
        "autoInstallIdeExtension": "auto_install_ide_extension",
        "hasIdeOnboardingBeenShown": "has_ide_onboarding_been_shown",
        "ideHintShownCount": "ide_hint_shown_count",
        "hasIdeAutoConnectDialogBeenShown": "has_ide_auto_connect_dialog_been_shown",
        "tipsHistory": "tips_history",
        "companion": "companion",
        "companionMuted": "companion_muted",
        "feedbackSurveyState": "feedback_survey_state",
        "transcriptShareDismissed": "transcript_share_dismissed",
        "memoryUsageCount": "memory_usage_count",
        "hasShownS1MWelcomeV2": "has_shown_s1m_welcome_v2",
        "s1mAccessCache": "s1m_access_cache",
        "s1mNonSubscriberAccessCache": "s1m_non_subscriber_access_cache",
        "passesEligibilityCache": "passes_eligibility_cache",
        "groveConfigCache": "grove_config_cache",
        "passesUpsellSeenCount": "passes_upsell_seen_count",
        "hasVisitedPasses": "has_visited_passes",
        "passesLastSeenRemaining": "passes_last_seen_remaining",
        "overageCreditGrantCache": "overage_credit_grant_cache",
        "overageCreditUpsellSeenCount": "overage_credit_upsell_seen_count",
        "hasVisitedExtraUsage": "has_visited_extra_usage",
        "voiceNoticeSeenCount": "voice_notice_seen_count",
        "voiceLangHintShownCount": "voice_lang_hint_shown_count",
        "voiceLangHintLastLanguage": "voice_lang_hint_last_language",
        "voiceFooterHintSeenCount": "voice_footer_hint_seen_count",
        "opus1mMergeNoticeSeenCount": "opus1m_merge_notice_seen_count",
        "experimentNoticesSeenCount": "experiment_notices_seen_count",
        "hasShownOpusPlanWelcome": "has_shown_opus_plan_welcome",
        "promptQueueUseCount": "prompt_queue_use_count",
        "btwUseCount": "btw_use_count",
        "lastPlanModeUse": "last_plan_mode_use",
        "subscriptionNoticeCount": "subscription_notice_count",
        "hasAvailableSubscription": "has_available_subscription",
        "subscriptionUpsellShownCount": "subscription_upsell_shown_count",
        "recommendedSubscription": "recommended_subscription",
        "todoFeatureEnabled": "todo_feature_enabled",
        "showExpandedTodos": "show_expanded_todos",
        "showSpinnerTree": "show_spinner_tree",
        "firstStartTime": "first_start_time",
        "messageIdleNotifThresholdMs": "message_idle_notif_threshold_ms",
        "githubActionSetupCount": "github_action_setup_count",
        "slackAppInstallCount": "slack_app_install_count",
        "fileCheckpointingEnabled": "file_checkpointing_enabled",
        "terminalProgressBarEnabled": "terminal_progress_bar_enabled",
        "showStatusInTerminalTab": "show_status_in_terminal_tab",
        "taskCompleteNotifEnabled": "task_complete_notif_enabled",
        "inputNeededNotifEnabled": "input_needed_notif_enabled",
        "agentPushNotifEnabled": "agent_push_notif_enabled",
        "claudeCodeFirstTokenDate": "claude_code_first_token_date",
        "modelSwitchCalloutDismissed": "model_switch_callout_dismissed",
        "modelSwitchCalloutLastShown": "model_switch_callout_last_shown",
        "modelSwitchCalloutVersion": "model_switch_callout_version",
        "effortCalloutDismissed": "effort_callout_dismissed",
        "effortCalloutV2Dismissed": "effort_callout_v2_dismissed",
        "remoteDialogSeen": "remote_dialog_seen",
        "bridgeOauthDeadExpiresAt": "bridge_oauth_dead_expires_at",
        "bridgeOauthDeadFailCount": "bridge_oauth_dead_fail_count",
        "desktopUpsellSeenCount": "desktop_upsell_seen_count",
        "desktopUpsellDismissed": "desktop_upsell_dismissed",
        "idleReturnDismissed": "idle_return_dismissed",
        "opusProMigrationComplete": "opus_pro_migration_complete",
        "opusProMigrationTimestamp": "opus_pro_migration_timestamp",
        "sonnet1m45MigrationComplete": "sonnet1m45_migration_complete",
        "legacyOpusMigrationTimestamp": "legacy_opus_migration_timestamp",
        "sonnet45To46MigrationTimestamp": "sonnet45_to46_migration_timestamp",
        "cachedStatsigGates": "cached_statsig_gates",
        "cachedDynamicConfigs": "cached_dynamic_configs",
        "cachedGrowthBookFeatures": "cached_growth_book_features",
        "growthBookOverrides": "growth_book_overrides",
        "lastShownEmergencyTip": "last_shown_emergency_tip",
        "respectGitignore": "respect_gitignore",
        "copyFullResponse": "copy_full_response",
        "copyOnSelect": "copy_on_select",
        "githubRepoPaths": "github_repo_paths",
        "deepLinkTerminal": "deep_link_terminal",
        "iterm2It2SetupComplete": "iterm2_it2_setup_complete",
        "preferTmuxOverIterm2": "prefer_tmux_over_iterm2",
        "skillUsage": "skill_usage",
        "officialMarketplaceAutoInstallAttempted": "official_marketplace_auto_install_attempted",
        "officialMarketplaceAutoInstalled": "official_marketplace_auto_installed",
        "officialMarketplaceAutoInstallFailReason": "official_marketplace_auto_install_fail_reason",
        "officialMarketplaceAutoInstallRetryCount": "official_marketplace_auto_install_retry_count",
        "officialMarketplaceAutoInstallLastAttemptTime": "official_marketplace_auto_install_last_attempt_time",
        "officialMarketplaceAutoInstallNextRetryTime": "official_marketplace_auto_install_next_retry_time",
        "hasCompletedClaudeInChromeOnboarding": "has_completed_claude_in_chrome_onboarding",
        "claudeInChromeDefaultEnabled": "claude_in_chrome_default_enabled",
        "cachedChromeExtensionInstalled": "cached_chrome_extension_installed",
        "chromeExtension": "chrome_extension",
        "lspRecommendationDisabled": "lsp_recommendation_disabled",
        "lspRecommendationNeverPlugins": "lsp_recommendation_never_plugins",
        "lspRecommendationIgnoredCount": "lsp_recommendation_ignored_count",
        "claudeCodeHints": "claude_code_hints",
        "permissionExplainerEnabled": "permission_explainer_enabled",
        "teammateMode": "teammate_mode",
        "teammateDefaultModel": "teammate_default_model",
        "prStatusFooterEnabled": "pr_status_footer_enabled",
        "tungstenPanelVisible": "tungsten_panel_visible",
        "penguinModeOrgEnabled": "penguin_mode_org_enabled",
        "startupPrefetchedAt": "startup_prefetched_at",
        "remoteControlAtStartup": "remote_control_at_startup",
        "cachedExtraUsageDisabledReason": "cached_extra_usage_disabled_reason",
        "autoPermissionsNotificationCount": "auto_permissions_notification_count",
        "speculationEnabled": "speculation_enabled",
        "clientDataCache": "client_data_cache",
        "additionalModelOptionsCache": "additional_model_options_cache",
        "metricsStatusCache": "metrics_status_cache",
        "migrationVersion": "migration_version",
        "projects": "projects",
        "apiKeyHelper": "api_key_helper",
    }
    mapped: dict[str, Any] = {}
    for camel_key, value in d.items():
        snake_key = _CAMEL_TO_SNAKE.get(camel_key, camel_key)
        mapped[snake_key] = value

    # Apply to defaults
    for key, value in mapped.items():
        if hasattr(defaults, key):
            setattr(defaults, key, value)
    return defaults


def _global_config_to_dict(config: GlobalConfig) -> dict[str, Any]:
    """Serialize GlobalConfig back to camelCase JSON dict."""
    _SNAKE_TO_CAMEL: dict[str, str] = {
        "num_startups": "numStartups",
        "install_method": "installMethod",
        "auto_updates": "autoUpdates",
        "auto_updates_protected_for_native": "autoUpdatesProtectedForNative",
        "doctor_shown_at_session": "doctorShownAtSession",
        "user_id": "userID",
        "theme": "theme",
        "has_completed_onboarding": "hasCompletedOnboarding",
        "last_onboarding_version": "lastOnboardingVersion",
        "last_release_notes_seen": "lastReleaseNotesSeen",
        "changelog_last_fetched": "changelogLastFetched",
        "cached_changelog": "cachedChangelog",
        "mcp_servers": "mcpServers",
        "claude_ai_mcp_ever_connected": "claudeAiMcpEverConnected",
        "preferred_notif_channel": "preferredNotifChannel",
        "custom_notify_command": "customNotifyCommand",
        "verbose": "verbose",
        "custom_api_key_responses": "customApiKeyResponses",
        "primary_api_key": "primaryApiKey",
        "has_acknowledged_cost_threshold": "hasAcknowledgedCostThreshold",
        "has_seen_undercover_auto_notice": "hasSeenUndercoverAutoNotice",
        "has_seen_ultraplan_terms": "hasSeenUltraplanTerms",
        "has_reset_auto_mode_opt_in_for_default_offer": "hasResetAutoModeOptInForDefaultOffer",
        "oauth_account": "oauthAccount",
        "iterm2_key_binding_installed": "iterm2KeyBindingInstalled",
        "editor_mode": "editorMode",
        "bypass_permissions_mode_accepted": "bypassPermissionsModeAccepted",
        "has_used_backslash_return": "hasUsedBackslashReturn",
        "auto_compact_enabled": "autoCompactEnabled",
        "show_turn_duration": "showTurnDuration",
        "env": "env",
        "has_seen_tasks_hint": "hasSeenTasksHint",
        "has_used_stash": "hasUsedStash",
        "has_used_background_task": "hasUsedBackgroundTask",
        "queued_command_up_hint_count": "queuedCommandUpHintCount",
        "diff_tool": "diffTool",
        "iterm2_setup_in_progress": "iterm2SetupInProgress",
        "iterm2_backup_path": "iterm2BackupPath",
        "apple_terminal_backup_path": "appleTerminalBackupPath",
        "apple_terminal_setup_in_progress": "appleTerminalSetupInProgress",
        "shift_enter_key_binding_installed": "shiftEnterKeyBindingInstalled",
        "option_as_meta_key_installed": "optionAsMetaKeyInstalled",
        "auto_connect_ide": "autoConnectIde",
        "auto_install_ide_extension": "autoInstallIdeExtension",
        "has_ide_onboarding_been_shown": "hasIdeOnboardingBeenShown",
        "ide_hint_shown_count": "ideHintShownCount",
        "has_ide_auto_connect_dialog_been_shown": "hasIdeAutoConnectDialogBeenShown",
        "tips_history": "tipsHistory",
        "companion": "companion",
        "companion_muted": "companionMuted",
        "feedback_survey_state": "feedbackSurveyState",
        "transcript_share_dismissed": "transcriptShareDismissed",
        "memory_usage_count": "memoryUsageCount",
        "has_shown_s1m_welcome_v2": "hasShownS1MWelcomeV2",
        "s1m_access_cache": "s1mAccessCache",
        "s1m_non_subscriber_access_cache": "s1mNonSubscriberAccessCache",
        "passes_eligibility_cache": "passesEligibilityCache",
        "grove_config_cache": "groveConfigCache",
        "passes_upsell_seen_count": "passesUpsellSeenCount",
        "has_visited_passes": "hasVisitedPasses",
        "passes_last_seen_remaining": "passesLastSeenRemaining",
        "overage_credit_grant_cache": "overageCreditGrantCache",
        "overage_credit_upsell_seen_count": "overageCreditUpsellSeenCount",
        "has_visited_extra_usage": "hasVisitedExtraUsage",
        "voice_notice_seen_count": "voiceNoticeSeenCount",
        "voice_lang_hint_shown_count": "voiceLangHintShownCount",
        "voice_lang_hint_last_language": "voiceLangHintLastLanguage",
        "voice_footer_hint_seen_count": "voiceFooterHintSeenCount",
        "opus1m_merge_notice_seen_count": "opus1mMergeNoticeSeenCount",
        "experiment_notices_seen_count": "experimentNoticesSeenCount",
        "has_shown_opus_plan_welcome": "hasShownOpusPlanWelcome",
        "prompt_queue_use_count": "promptQueueUseCount",
        "btw_use_count": "btwUseCount",
        "last_plan_mode_use": "lastPlanModeUse",
        "subscription_notice_count": "subscriptionNoticeCount",
        "has_available_subscription": "hasAvailableSubscription",
        "subscription_upsell_shown_count": "subscriptionUpsellShownCount",
        "recommended_subscription": "recommendedSubscription",
        "todo_feature_enabled": "todoFeatureEnabled",
        "show_expanded_todos": "showExpandedTodos",
        "show_spinner_tree": "showSpinnerTree",
        "first_start_time": "firstStartTime",
        "message_idle_notif_threshold_ms": "messageIdleNotifThresholdMs",
        "github_action_setup_count": "githubActionSetupCount",
        "slack_app_install_count": "slackAppInstallCount",
        "file_checkpointing_enabled": "fileCheckpointingEnabled",
        "terminal_progress_bar_enabled": "terminalProgressBarEnabled",
        "show_status_in_terminal_tab": "showStatusInTerminalTab",
        "task_complete_notif_enabled": "taskCompleteNotifEnabled",
        "input_needed_notif_enabled": "inputNeededNotifEnabled",
        "agent_push_notif_enabled": "agentPushNotifEnabled",
        "claude_code_first_token_date": "claudeCodeFirstTokenDate",
        "model_switch_callout_dismissed": "modelSwitchCalloutDismissed",
        "model_switch_callout_last_shown": "modelSwitchCalloutLastShown",
        "model_switch_callout_version": "modelSwitchCalloutVersion",
        "effort_callout_dismissed": "effortCalloutDismissed",
        "effort_callout_v2_dismissed": "effortCalloutV2Dismissed",
        "remote_dialog_seen": "remoteDialogSeen",
        "bridge_oauth_dead_expires_at": "bridgeOauthDeadExpiresAt",
        "bridge_oauth_dead_fail_count": "bridgeOauthDeadFailCount",
        "desktop_upsell_seen_count": "desktopUpsellSeenCount",
        "desktop_upsell_dismissed": "desktopUpsellDismissed",
        "idle_return_dismissed": "idleReturnDismissed",
        "opus_pro_migration_complete": "opusProMigrationComplete",
        "opus_pro_migration_timestamp": "opusProMigrationTimestamp",
        "sonnet1m45_migration_complete": "sonnet1m45MigrationComplete",
        "legacy_opus_migration_timestamp": "legacyOpusMigrationTimestamp",
        "sonnet45_to46_migration_timestamp": "sonnet45To46MigrationTimestamp",
        "cached_statsig_gates": "cachedStatsigGates",
        "cached_dynamic_configs": "cachedDynamicConfigs",
        "cached_growth_book_features": "cachedGrowthBookFeatures",
        "growth_book_overrides": "growthBookOverrides",
        "last_shown_emergency_tip": "lastShownEmergencyTip",
        "respect_gitignore": "respectGitignore",
        "copy_full_response": "copyFullResponse",
        "copy_on_select": "copyOnSelect",
        "github_repo_paths": "githubRepoPaths",
        "deep_link_terminal": "deepLinkTerminal",
        "iterm2_it2_setup_complete": "iterm2It2SetupComplete",
        "prefer_tmux_over_iterm2": "preferTmuxOverIterm2",
        "skill_usage": "skillUsage",
        "official_marketplace_auto_install_attempted": "officialMarketplaceAutoInstallAttempted",
        "official_marketplace_auto_installed": "officialMarketplaceAutoInstalled",
        "official_marketplace_auto_install_fail_reason": "officialMarketplaceAutoInstallFailReason",
        "official_marketplace_auto_install_retry_count": "officialMarketplaceAutoInstallRetryCount",
        "official_marketplace_auto_install_last_attempt_time": "officialMarketplaceAutoInstallLastAttemptTime",
        "official_marketplace_auto_install_next_retry_time": "officialMarketplaceAutoInstallNextRetryTime",
        "has_completed_claude_in_chrome_onboarding": "hasCompletedClaudeInChromeOnboarding",
        "claude_in_chrome_default_enabled": "claudeInChromeDefaultEnabled",
        "cached_chrome_extension_installed": "cachedChromeExtensionInstalled",
        "chrome_extension": "chromeExtension",
        "lsp_recommendation_disabled": "lspRecommendationDisabled",
        "lsp_recommendation_never_plugins": "lspRecommendationNeverPlugins",
        "lsp_recommendation_ignored_count": "lspRecommendationIgnoredCount",
        "claude_code_hints": "claudeCodeHints",
        "permission_explainer_enabled": "permissionExplainerEnabled",
        "teammate_mode": "teammateMode",
        "teammate_default_model": "teammateDefaultModel",
        "pr_status_footer_enabled": "prStatusFooterEnabled",
        "tungsten_panel_visible": "tungstenPanelVisible",
        "penguin_mode_org_enabled": "penguinModeOrgEnabled",
        "startup_prefetched_at": "startupPrefetchedAt",
        "remote_control_at_startup": "remoteControlAtStartup",
        "cached_extra_usage_disabled_reason": "cachedExtraUsageDisabledReason",
        "auto_permissions_notification_count": "autoPermissionsNotificationCount",
        "speculation_enabled": "speculationEnabled",
        "client_data_cache": "clientDataCache",
        "additional_model_options_cache": "additionalModelOptionsCache",
        "metrics_status_cache": "metricsStatusCache",
        "migration_version": "migrationVersion",
        "projects": "projects",
        "api_key_helper": "apiKeyHelper",
    }
    import dataclasses
    result: dict[str, Any] = {}
    for f in dataclasses.fields(config):
        value = getattr(config, f.name)
        if value is None:
            continue
        camel_key = _SNAKE_TO_CAMEL.get(f.name, f.name)
        result[camel_key] = _to_json_serializable(value)
    return result


def _project_config_to_dict(config: ProjectConfig) -> dict[str, Any]:
    """Serialize ProjectConfig to camelCase JSON dict."""
    import dataclasses
    _MAP: dict[str, str] = {
        "allowed_tools": "allowedTools",
        "mcp_context_uris": "mcpContextUris",
        "mcp_servers": "mcpServers",
        "last_api_duration": "lastAPIDuration",
        "last_api_duration_without_retries": "lastAPIDurationWithoutRetries",
        "last_tool_duration": "lastToolDuration",
        "last_cost": "lastCost",
        "last_duration": "lastDuration",
        "last_lines_added": "lastLinesAdded",
        "last_lines_removed": "lastLinesRemoved",
        "last_total_input_tokens": "lastTotalInputTokens",
        "last_total_output_tokens": "lastTotalOutputTokens",
        "last_total_cache_creation_input_tokens": "lastTotalCacheCreationInputTokens",
        "last_total_cache_read_input_tokens": "lastTotalCacheReadInputTokens",
        "last_total_web_search_requests": "lastTotalWebSearchRequests",
        "last_fps_average": "lastFpsAverage",
        "last_fps_low1_pct": "lastFpsLow1Pct",
        "last_session_id": "lastSessionId",
        "last_model_usage": "lastModelUsage",
        "last_session_metrics": "lastSessionMetrics",
        "example_files": "exampleFiles",
        "example_files_generated_at": "exampleFilesGeneratedAt",
        "has_trust_dialog_accepted": "hasTrustDialogAccepted",
        "has_completed_project_onboarding": "hasCompletedProjectOnboarding",
        "project_onboarding_seen_count": "projectOnboardingSeenCount",
        "has_claude_md_external_includes_approved": "hasClaudeMdExternalIncludesApproved",
        "has_claude_md_external_includes_warning_shown": "hasClaudeMdExternalIncludesWarningShown",
        "enabled_mcpjson_servers": "enabledMcpjsonServers",
        "disabled_mcpjson_servers": "disabledMcpjsonServers",
        "enable_all_project_mcp_servers": "enableAllProjectMcpServers",
        "disabled_mcp_servers": "disabledMcpServers",
        "enabled_mcp_servers": "enabledMcpServers",
        "active_worktree_session": "activeWorktreeSession",
        "remote_control_spawn_mode": "remoteControlSpawnMode",
    }
    result: dict[str, Any] = {}
    for f in dataclasses.fields(config):
        value = getattr(config, f.name)
        if value is None:
            continue
        camel_key = _MAP.get(f.name, f.name)
        result[camel_key] = _to_json_serializable(value)
    return result


def _dict_to_project_config(d: dict[str, Any]) -> ProjectConfig:
    pc = ProjectConfig()
    _MAP: dict[str, str] = {
        "allowedTools": "allowed_tools",
        "mcpContextUris": "mcp_context_uris",
        "mcpServers": "mcp_servers",
        "lastAPIDuration": "last_api_duration",
        "lastAPIDurationWithoutRetries": "last_api_duration_without_retries",
        "lastToolDuration": "last_tool_duration",
        "lastCost": "last_cost",
        "lastDuration": "last_duration",
        "lastLinesAdded": "last_lines_added",
        "lastLinesRemoved": "last_lines_removed",
        "lastTotalInputTokens": "last_total_input_tokens",
        "lastTotalOutputTokens": "last_total_output_tokens",
        "lastTotalCacheCreationInputTokens": "last_total_cache_creation_input_tokens",
        "lastTotalCacheReadInputTokens": "last_total_cache_read_input_tokens",
        "lastTotalWebSearchRequests": "last_total_web_search_requests",
        "lastFpsAverage": "last_fps_average",
        "lastFpsLow1Pct": "last_fps_low1_pct",
        "lastSessionId": "last_session_id",
        "lastModelUsage": "last_model_usage",
        "lastSessionMetrics": "last_session_metrics",
        "exampleFiles": "example_files",
        "exampleFilesGeneratedAt": "example_files_generated_at",
        "hasTrustDialogAccepted": "has_trust_dialog_accepted",
        "hasCompletedProjectOnboarding": "has_completed_project_onboarding",
        "projectOnboardingSeenCount": "project_onboarding_seen_count",
        "hasClaudeMdExternalIncludesApproved": "has_claude_md_external_includes_approved",
        "hasClaudeMdExternalIncludesWarningShown": "has_claude_md_external_includes_warning_shown",
        "enabledMcpjsonServers": "enabled_mcpjson_servers",
        "disabledMcpjsonServers": "disabled_mcpjson_servers",
        "enableAllProjectMcpServers": "enable_all_project_mcp_servers",
        "disabledMcpServers": "disabled_mcp_servers",
        "enabledMcpServers": "enabled_mcp_servers",
        "activeWorktreeSession": "active_worktree_session",
        "remoteControlSpawnMode": "remote_control_spawn_mode",
    }
    for camel_key, value in d.items():
        snake_key = _MAP.get(camel_key, camel_key)
        if hasattr(pc, snake_key):
            setattr(pc, snake_key, value)
    # Normalize allowedTools: may be a JSON string in old configs
    if isinstance(pc.allowed_tools, str):
        try:
            pc.allowed_tools = json.loads(pc.allowed_tools) or []
        except Exception:
            pc.allowed_tools = []
    return pc


def _migrate_config_fields(config: GlobalConfig) -> GlobalConfig:
    """Migrate old autoUpdaterStatus → installMethod/autoUpdates (legacy compat)."""
    if config.install_method is not None:
        return config
    # Legacy field may be present as a raw dict key from JSON parsing
    return config


def _remove_project_history(projects: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip the legacy 'history' field from project entries."""
    if not projects:
        return projects
    cleaned: dict[str, Any] = {}
    needs_cleaning = False
    for path, proj in projects.items():
        if isinstance(proj, dict) and "history" in proj:
            needs_cleaning = True
            cleaned[path] = {k: v for k, v in proj.items() if k != "history"}
        else:
            cleaned[path] = proj
    return cleaned if needs_cleaning else projects


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _GlobalConfigCache:
    config: GlobalConfig | None = None
    mtime: float = 0.0


_global_config_cache = _GlobalConfigCache()
_last_read_file_stats: dict[str, float] | None = None  # {"mtime": ..., "size": ...}
_config_cache_hits = 0
_config_cache_misses = 0
_global_config_write_count = 0

CONFIG_WRITE_DISPLAY_THRESHOLD = 20


def get_global_config_write_count() -> int:
    return _global_config_write_count


def _write_through_global_config_cache(config: GlobalConfig) -> None:
    global _global_config_cache
    _global_config_cache = _GlobalConfigCache(config=config, mtime=time.time() * 1000)


# ---------------------------------------------------------------------------
# Auth-loss guard
# ---------------------------------------------------------------------------

def _would_lose_auth_state(fresh: dict[str, Any]) -> bool:
    """Return True if `fresh` config would destroy cached auth we still have."""
    cached = _global_config_cache.config
    if not cached:
        return False
    lost_oauth = (
        cached.oauth_account is not None
        and fresh.get("oauthAccount") is None
    )
    lost_onboarding = (
        cached.has_completed_onboarding is True
        and fresh.get("hasCompletedOnboarding") is not True
    )
    return lost_oauth or lost_onboarding


# ---------------------------------------------------------------------------
# Low-level read/write
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _write_file(path: str, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file then rename for atomicity
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
        # Set secure permissions (owner read/write only)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _get_config_from_file(
    file: str,
    create_default: Callable[[], Any],
    throw_on_invalid: bool = False,
) -> Any:
    global _inside_get_config

    if not _config_reading_allowed and os.environ.get("NODE_ENV") != "test":
        raise RuntimeError("Config accessed before allowed.")

    content = _read_file(file)
    if content is None:
        backup = _find_most_recent_backup(file)
        if backup:
            sys.stderr.write(
                f"\nClaude configuration file not found at: {file}\n"
                f"A backup file exists at: {backup}\n"
                f'You can manually restore it by running: cp "{backup}" "{file}"\n\n'
            )
        return create_default()

    try:
        parsed = _json_loads(_strip_bom(content))
        default = create_default()
        if isinstance(parsed, dict) and hasattr(default, "__dataclass_fields__"):
            # Merge parsed into defaults
            return _global_config_dict_to_obj({**_global_config_to_dict(default), **parsed})
        return default
    except json.JSONDecodeError as exc:
        err = ConfigParseError(str(exc), file, create_default())
        if throw_on_invalid:
            raise err

        sys.stderr.write(
            f"\nClaude configuration file at {file} is corrupted: {exc}\n"
        )

        # Backup corrupted file
        if not _inside_get_config:
            _inside_get_config = True
            try:
                backup_dir = Path(_get_config_backup_dir())
                backup_dir.mkdir(parents=True, exist_ok=True)
                file_base = Path(file).name
                corrupted_backup = backup_dir / f"{file_base}.corrupted.{int(time.time() * 1000)}"
                try:
                    shutil.copy2(file, corrupted_backup)
                except OSError:
                    pass
            finally:
                _inside_get_config = False

        backup = _find_most_recent_backup(file)
        if backup:
            sys.stderr.write(
                f"A backup file exists at: {backup}\n"
                f'You can manually restore it by running: cp "{backup}" "{file}"\n\n'
            )

        return create_default()


def _save_config_raw(file: str, config_dict: dict[str, Any], default_dict: dict[str, Any]) -> None:
    """Filter out default-valued keys and write JSON to file."""
    filtered = {
        k: v for k, v in config_dict.items()
        if _json_dumps(v) != _json_dumps(default_dict.get(k))
    }
    _write_file(file, _json_dumps(filtered, indent=2))


def _save_config_with_lock(
    file: str,
    create_default: Callable[[], Any],
    merge_fn: Callable[[Any], Any],
) -> bool:
    """Write config under a file lock. Returns True if a write was performed."""
    global _global_config_write_count, _last_read_file_stats

    lock_path = f"{file}.lock"
    Path(file).parent.mkdir(parents=True, exist_ok=True)

    lock_file = None
    with _write_lock:
        try:
            lock_file = _acquire_file_lock(lock_path)

            # Re-read current config inside the lock
            current = _get_config_from_file(file, create_default)
            current_dict = _global_config_to_dict(current) if isinstance(current, GlobalConfig) else {}

            if file == _get_global_claude_file() and _would_lose_auth_state(current_dict):
                return False

            merged = merge_fn(current)

            # Skip if no changes
            if merged is current:
                return False

            default = create_default()
            merged_dict = _global_config_to_dict(merged) if isinstance(merged, GlobalConfig) else {}
            default_dict = _global_config_to_dict(default) if isinstance(default, GlobalConfig) else {}

            # Create backup before writing
            _maybe_create_backup(file)

            _save_config_raw(file, merged_dict, default_dict)
            if file == _get_global_claude_file():
                _global_config_write_count += 1
            return True
        finally:
            if lock_file is not None:
                _release_file_lock(lock_file)
            try:
                os.unlink(lock_path)
            except OSError:
                pass


def _maybe_create_backup(file: str) -> None:
    """Create a timestamped backup of `file` if no recent backup exists."""
    MIN_BACKUP_INTERVAL_MS = 60_000
    MAX_BACKUPS = 5

    backup_dir = Path(_get_config_backup_dir())
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    file_base = Path(file).name
    try:
        existing = sorted(
            f.name for f in backup_dir.iterdir()
            if f.name.startswith(f"{file_base}.backup.")
        )
    except OSError:
        existing = []

    most_recent_ts = 0
    if existing:
        try:
            most_recent_ts = int(existing[-1].split(".backup.")[-1])
        except ValueError:
            most_recent_ts = 0

    now_ms = int(time.time() * 1000)
    if now_ms - most_recent_ts >= MIN_BACKUP_INTERVAL_MS:
        backup_path = backup_dir / f"{file_base}.backup.{now_ms}"
        try:
            shutil.copy2(file, backup_path)
        except OSError:
            pass

    # Prune old backups
    try:
        all_backups = sorted(
            f for f in backup_dir.iterdir()
            if f.name.startswith(f"{file_base}.backup.")
        )
        for old in all_backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_global_config() -> GlobalConfig:
    """Return the cached GlobalConfig, loading from disk on first call."""
    global _config_cache_hits, _config_cache_misses

    if os.environ.get("NODE_ENV") == "test":
        return _TEST_GLOBAL_CONFIG

    if _global_config_cache.config is not None:
        _config_cache_hits += 1
        return _global_config_cache.config

    _config_cache_misses += 1
    file = _get_global_claude_file()
    try:
        stat = os.stat(file)
        mtime_ms = stat.st_mtime * 1000
        size = stat.st_size
    except OSError:
        mtime_ms = time.time() * 1000
        size = 0

    config = _migrate_config_fields(
        _get_config_from_file(file, create_default_global_config)
    )
    _global_config_cache.config = config
    _global_config_cache.mtime = mtime_ms
    return config


def save_global_config(updater: Callable[[GlobalConfig], GlobalConfig]) -> None:
    """Atomically update the global config using an updater function."""
    global _global_config_write_count

    if os.environ.get("NODE_ENV") == "test":
        config = updater(_TEST_GLOBAL_CONFIG)
        if config is not _TEST_GLOBAL_CONFIG:
            import dataclasses
            for f in dataclasses.fields(config):
                setattr(_TEST_GLOBAL_CONFIG, f.name, getattr(config, f.name))
        return

    written: GlobalConfig | None = None

    def merge_fn(current: GlobalConfig) -> GlobalConfig:
        nonlocal written
        result = updater(current)
        if result is current:
            return current
        # Strip project history from projects dict
        raw = _global_config_to_dict(result)
        raw["projects"] = _remove_project_history(raw.get("projects"))
        result = _global_config_dict_to_obj(raw)
        written = result
        return result

    try:
        did_write = _save_config_with_lock(
            _get_global_claude_file(),
            create_default_global_config,
            merge_fn,
        )
        if did_write and written is not None:
            _write_through_global_config_cache(written)
    except Exception as exc:
        # Fallback: non-locked write
        current = _get_config_from_file(
            _get_global_claude_file(), create_default_global_config
        )
        current_dict = _global_config_to_dict(current)
        if _would_lose_auth_state(current_dict):
            return
        result = updater(current)
        if result is current:
            return
        raw = _global_config_to_dict(result)
        raw["projects"] = _remove_project_history(raw.get("projects"))
        merged = _global_config_dict_to_obj(raw)
        default_dict = _global_config_to_dict(create_default_global_config())
        _save_config_raw(_get_global_claude_file(), _global_config_to_dict(merged), default_dict)
        _global_config_write_count += 1
        _write_through_global_config_cache(merged)


# Memoized (session-stable) project path for config key
@lru_cache(maxsize=1)
def get_project_path_for_config() -> str:
    """Return the canonical project path used as the key in config.projects."""
    original_cwd = _get_original_cwd()
    git_root = _find_canonical_git_root(original_cwd)
    if git_root:
        return _normalize_path_for_config_key(git_root)
    return _normalize_path_for_config_key(str(Path(original_cwd).resolve()))


def get_current_project_config() -> ProjectConfig:
    """Return the ProjectConfig for the current working directory."""
    if os.environ.get("NODE_ENV") == "test":
        return _TEST_PROJECT_CONFIG

    absolute_path = get_project_path_for_config()
    config = get_global_config()

    if not config.projects:
        return DEFAULT_PROJECT_CONFIG

    raw = config.projects.get(absolute_path)
    if raw is None:
        return DEFAULT_PROJECT_CONFIG

    if isinstance(raw, dict):
        return _dict_to_project_config(raw)
    return raw


def save_current_project_config(
    updater: Callable[[ProjectConfig], ProjectConfig],
) -> None:
    """Atomically update the current project's config."""
    if os.environ.get("NODE_ENV") == "test":
        config = updater(_TEST_PROJECT_CONFIG)
        if config is not _TEST_PROJECT_CONFIG:
            import dataclasses
            for f in dataclasses.fields(config):
                setattr(_TEST_PROJECT_CONFIG, f.name, getattr(config, f.name))
        return

    absolute_path = get_project_path_for_config()
    written: GlobalConfig | None = None

    def merge_fn(current: GlobalConfig) -> GlobalConfig:
        nonlocal written
        projects = current.projects or {}
        raw = projects.get(absolute_path)
        current_project = _dict_to_project_config(raw) if isinstance(raw, dict) else (raw or DEFAULT_PROJECT_CONFIG)
        new_project = updater(current_project)
        if new_project is current_project:
            return current
        updated_projects = {**projects, absolute_path: _project_config_to_dict(new_project)}
        import dataclasses
        result = dataclasses.replace(current, projects=updated_projects)
        written = result
        return result

    try:
        did_write = _save_config_with_lock(
            _get_global_claude_file(),
            create_default_global_config,
            merge_fn,
        )
        if did_write and written is not None:
            _write_through_global_config_cache(written)
    except Exception:
        current = _get_config_from_file(
            _get_global_claude_file(), create_default_global_config
        )
        current_dict = _global_config_to_dict(current)
        if _would_lose_auth_state(current_dict):
            return
        projects = current.projects or {}
        raw = projects.get(absolute_path)
        current_project = _dict_to_project_config(raw) if isinstance(raw, dict) else (raw or DEFAULT_PROJECT_CONFIG)
        new_project = updater(current_project)
        if new_project is current_project:
            return
        import dataclasses
        merged = dataclasses.replace(
            current,
            projects={**projects, absolute_path: _project_config_to_dict(new_project)},
        )
        default_dict = _global_config_to_dict(create_default_global_config())
        _save_config_raw(_get_global_claude_file(), _global_config_to_dict(merged), default_dict)
        _write_through_global_config_cache(merged)


# ---------------------------------------------------------------------------
# Trust dialog
# ---------------------------------------------------------------------------

_trust_accepted = False


def reset_trust_dialog_accepted_cache_for_testing() -> None:
    global _trust_accepted
    _trust_accepted = False


def check_has_trust_dialog_accepted() -> bool:
    global _trust_accepted
    if _trust_accepted:
        return True
    result = _compute_trust_dialog_accepted()
    if result:
        _trust_accepted = True
    return result


def _compute_trust_dialog_accepted() -> bool:
    if _get_session_trust_accepted():
        return True

    config = get_global_config()
    project_path = get_project_path_for_config()
    raw = (config.projects or {}).get(project_path)
    proj = _dict_to_project_config(raw) if isinstance(raw, dict) else raw
    if proj and proj.has_trust_dialog_accepted:
        return True

    current_path = _normalize_path_for_config_key(_get_cwd())
    while True:
        raw = (config.projects or {}).get(current_path)
        proj = _dict_to_project_config(raw) if isinstance(raw, dict) else raw
        if proj and proj.has_trust_dialog_accepted:
            return True
        parent = _normalize_path_for_config_key(str(Path(current_path).parent))
        if parent == current_path:
            break
        current_path = parent
    return False


def is_path_trusted(dir_: str) -> bool:
    """Return True if `dir_` or any ancestor has trust persisted."""
    config = get_global_config()
    current = _normalize_path_for_config_key(str(Path(dir_).resolve()))
    while True:
        raw = (config.projects or {}).get(current)
        proj = _dict_to_project_config(raw) if isinstance(raw, dict) else raw
        if proj and proj.has_trust_dialog_accepted:
            return True
        parent = _normalize_path_for_config_key(str(Path(current).parent))
        if parent == current:
            return False
        current = parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_custom_api_key_status(truncated_api_key: str) -> Literal["approved", "rejected", "new"]:
    config = get_global_config()
    responses = config.custom_api_key_responses or {}
    if truncated_api_key in (responses.get("approved") or []):
        return "approved"
    if truncated_api_key in (responses.get("rejected") or []):
        return "rejected"
    return "new"


def get_remote_control_at_startup() -> bool:
    explicit = get_global_config().remote_control_at_startup
    if explicit is not None:
        return explicit
    if _feature("CCR_AUTO_CONNECT"):
        try:
            from optimus.bridge.bridge_enabled import get_ccr_auto_connect_default
            if get_ccr_auto_connect_default():
                return True
        except ImportError:
            pass
    return False


# ---------------------------------------------------------------------------
# Auto-updater
# ---------------------------------------------------------------------------

@dataclass
class AutoUpdaterDisabledReason:
    type: Literal["development", "env", "config"]
    env_var: str | None = None


def format_auto_updater_disabled_reason(reason: AutoUpdaterDisabledReason) -> str:
    if reason.type == "development":
        return "development build"
    if reason.type == "env":
        return f"{reason.env_var} set"
    return "config"


def get_auto_updater_disabled_reason() -> AutoUpdaterDisabledReason | None:
    if os.environ.get("NODE_ENV") == "development":
        return AutoUpdaterDisabledReason(type="development")
    if _is_env_truthy(os.environ.get("DISABLE_AUTOUPDATER")):
        return AutoUpdaterDisabledReason(type="env", env_var="DISABLE_AUTOUPDATER")
    essential_reason = _get_essential_traffic_only_reason()
    if essential_reason:
        return AutoUpdaterDisabledReason(type="env", env_var=essential_reason)
    config = get_global_config()
    if (
        config.auto_updates is False
        and (
            config.install_method != "native"
            or config.auto_updates_protected_for_native is not True
        )
    ):
        return AutoUpdaterDisabledReason(type="config")
    return None


def is_auto_updater_disabled() -> bool:
    return get_auto_updater_disabled_reason() is not None


def should_skip_plugin_autoupdate() -> bool:
    return is_auto_updater_disabled() and not _is_env_truthy(
        os.environ.get("FORCE_AUTOUPDATE_PLUGINS")
    )


# ---------------------------------------------------------------------------
# User ID
# ---------------------------------------------------------------------------

def get_or_create_user_id() -> str:
    config = get_global_config()
    if config.user_id:
        return config.user_id
    user_id = _uuid_mod.uuid4().hex + _uuid_mod.uuid4().hex  # 32 hex bytes like randomBytes(32)
    save_global_config(lambda c: _replace_config(c, user_id=user_id))
    return user_id


def _replace_config(config: GlobalConfig, **kwargs: Any) -> GlobalConfig:
    import dataclasses
    return dataclasses.replace(config, **kwargs)


def record_first_start_time() -> None:
    config = get_global_config()
    if not config.first_start_time:
        first_start_time = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        save_global_config(
            lambda c: _replace_config(c, first_start_time=c.first_start_time or first_start_time)
        )


# ---------------------------------------------------------------------------
# Memory paths
# ---------------------------------------------------------------------------

def get_memory_path(memory_type: str) -> str:
    """Return the filesystem path for a given memory type."""
    from optimus.utils.env_utils import get_claude_config_home_dir
    cwd = _get_original_cwd()

    if memory_type == "User":
        return str(Path(get_claude_config_home_dir()) / "CLAUDE.md")
    if memory_type == "Local":
        return str(Path(cwd) / "CLAUDE.local.md")
    if memory_type == "Project":
        return str(Path(cwd) / "CLAUDE.md")
    if memory_type == "Managed":
        from optimus.utils.settings.managed_path import get_managed_file_path
        return str(Path(get_managed_file_path()) / "CLAUDE.md")
    if memory_type == "AutoMem":
        from optimus.memdir.paths import get_auto_mem_entrypoint
        return get_auto_mem_entrypoint()
    if memory_type == "TeamMem" and _feature("TEAMMEM"):
        from optimus.memdir.team_mem_paths import get_team_mem_entrypoint
        return get_team_mem_entrypoint()
    return ""


def get_managed_claude_rules_dir() -> str:
    from optimus.utils.settings.managed_path import get_managed_file_path
    return str(Path(get_managed_file_path()) / ".claude" / "rules")


def get_user_claude_rules_dir() -> str:
    return str(Path(_get_claude_config_home_dir()) / "rules")


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

# Separate mutable defaults for test environment
_TEST_GLOBAL_CONFIG: GlobalConfig = GlobalConfig(**{
    **{f.name: getattr(DEFAULT_GLOBAL_CONFIG, f.name)
       for f in __import__("dataclasses").fields(DEFAULT_GLOBAL_CONFIG)},
    "auto_updates": False,
})
_TEST_PROJECT_CONFIG: ProjectConfig = ProjectConfig(**{
    f.name: getattr(DEFAULT_PROJECT_CONFIG, f.name)
    for f in __import__("dataclasses").fields(DEFAULT_PROJECT_CONFIG)
})


def _set_global_config_cache_for_testing(config: GlobalConfig | None) -> None:
    global _global_config_cache
    _global_config_cache.config = config
    _global_config_cache.mtime = time.time() * 1000 if config else 0.0


# Re-export for downstream modules
__all__ = [
    "AccountInfo",
    "ActiveWorktreeSession",
    "AutoUpdaterDisabledReason",
    "CONFIG_WRITE_DISPLAY_THRESHOLD",
    "DEFAULT_GLOBAL_CONFIG",
    "DEFAULT_PROJECT_CONFIG",
    "DiffTool",
    "EditorMode",
    "GlobalConfig",
    "GLOBAL_CONFIG_KEYS",
    "GlobalConfigKey",
    "HistoryEntry",
    "ImageDimensions",
    "InstallMethod",
    "NotificationChannel",
    "OutputStyle",
    "PastedContent",
    "PROJECT_CONFIG_KEYS",
    "ProjectConfig",
    "ProjectConfigKey",
    "ReleaseChannel",
    "SerializedStructuredHistoryEntry",
    "ThemeSetting",
    "check_has_trust_dialog_accepted",
    "create_default_global_config",
    "enable_configs",
    "format_auto_updater_disabled_reason",
    "get_auto_updater_disabled_reason",
    "get_current_project_config",
    "get_custom_api_key_status",
    "get_global_config",
    "get_global_config_write_count",
    "get_memory_path",
    "get_managed_claude_rules_dir",
    "get_or_create_user_id",
    "get_project_path_for_config",
    "get_remote_control_at_startup",
    "get_user_claude_rules_dir",
    "is_auto_updater_disabled",
    "is_global_config_key",
    "is_path_trusted",
    "is_project_config_key",
    "record_first_start_time",
    "reset_trust_dialog_accepted_cache_for_testing",
    "save_current_project_config",
    "save_global_config",
    "should_skip_plugin_autoupdate",
]
