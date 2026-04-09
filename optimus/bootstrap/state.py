"""
Global session state — single source of truth for all session-scoped data.
Mirrors src/bootstrap/state.ts

DO NOT ADD MORE STATE HERE — be judicious with global state.
All state lives in the module-level STATE dict and is accessed via typed
getter/setter functions, mirroring the TypeScript pattern exactly.
"""
from __future__ import annotations

import os
import time
import uuid as _uuid_mod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optimus.types.ids import SessionId, as_session_id


# ---------------------------------------------------------------------------
# Signal (simple observer for session switch events)
# ---------------------------------------------------------------------------

class _Signal:
    def __init__(self) -> None:
        self._listeners: list[Any] = []

    def on(self, fn: Any) -> None:
        self._listeners.append(fn)

    def off(self, fn: Any) -> None:
        self._listeners = [f for f in self._listeners if f is not fn]

    def emit(self, *args: Any) -> None:
        for fn in list(self._listeners):
            fn(*args)


session_switched = _Signal()
cwd_state_changed = _Signal()


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

@dataclass
class State:
    original_cwd: str = ""
    project_root: str = ""
    total_cost_usd: float = 0.0
    total_api_duration: float = 0.0
    total_api_duration_without_retries: float = 0.0
    total_tool_duration: float = 0.0
    turn_hook_duration_ms: float = 0.0
    turn_tool_duration_ms: float = 0.0
    turn_classifier_duration_ms: float = 0.0
    turn_tool_count: int = 0
    turn_hook_count: int = 0
    turn_classifier_count: int = 0
    start_time: float = field(default_factory=lambda: time.time() * 1000)
    last_interaction_time: float = field(default_factory=lambda: time.time() * 1000)
    total_lines_added: int = 0
    total_lines_removed: int = 0
    has_unknown_model_cost: bool = False
    cwd: str = ""
    model_usage: dict[str, Any] = field(default_factory=dict)
    main_loop_model_override: Any = None
    initial_main_loop_model: Any = None
    model_strings: Any = None
    is_interactive: bool = False
    kairos_active: bool = False
    strict_tool_result_pairing: bool = False
    sdk_agent_progress_summaries_enabled: bool = False
    user_msg_opt_in: bool = False
    client_type: str = "cli"
    session_source: str | None = None
    question_preview_format: str | None = None
    flag_settings_path: str | None = None
    flag_settings_inline: dict[str, Any] | None = None
    allowed_setting_sources: list[str] = field(default_factory=lambda: [
        "userSettings", "projectSettings", "localSettings", "flagSettings", "policySettings"
    ])
    session_ingress_token: str | None = None
    oauth_token_from_fd: str | None = None
    api_key_from_fd: str | None = None
    # Telemetry
    meter: Any = None
    session_counter: Any = None
    loc_counter: Any = None
    pr_counter: Any = None
    commit_counter: Any = None
    cost_counter: Any = None
    token_counter: Any = None
    code_edit_tool_decision_counter: Any = None
    active_time_counter: Any = None
    stats_store: Any = None
    session_id: SessionId = field(default_factory=lambda: as_session_id(str(_uuid_mod.uuid4())))
    parent_session_id: SessionId | None = None
    # Logger
    logger_provider: Any = None
    event_logger: Any = None
    meter_provider: Any = None
    tracer_provider: Any = None
    # Agent color state
    agent_color_map: dict[str, str] = field(default_factory=dict)
    agent_color_index: int = 0
    # Last API request
    last_api_request: Any = None
    last_api_request_messages: Any = None
    last_classifier_requests: list[Any] | None = None
    cached_claude_md_content: str | None = None
    # Error log
    in_memory_error_log: list[dict[str, str]] = field(default_factory=list)
    # Session plugins
    inline_plugins: list[str] = field(default_factory=list)
    chrome_flag_override: bool | None = None
    use_cowork_plugins: bool = False
    session_bypass_permissions_mode: bool = False
    scheduled_tasks_enabled: bool = False
    session_cron_tasks: list[Any] = field(default_factory=list)
    session_created_teams: set[str] = field(default_factory=set)
    session_trust_accepted: bool = False
    session_persistence_disabled: bool = False
    has_exited_plan_mode: bool = False
    needs_plan_mode_exit_attachment: bool = False
    needs_auto_mode_exit_attachment: bool = False
    lsp_recommendation_shown_this_session: bool = False
    init_json_schema: dict[str, Any] | None = None
    registered_hooks: dict[str, list[Any]] | None = None
    plan_slug_cache: dict[str, str] = field(default_factory=dict)
    teleported_session_info: Any = None
    invoked_skills: dict[str, Any] = field(default_factory=dict)
    slow_operations: list[dict[str, Any]] = field(default_factory=list)
    sdk_betas: list[str] | None = None
    main_thread_agent_type: str | None = None
    is_remote_mode: bool = False
    direct_connect_server_url: str | None = None
    system_prompt_section_cache: dict[str, str | None] = field(default_factory=dict)
    last_emitted_date: str | None = None
    additional_directories_for_claude_md: list[str] = field(default_factory=list)
    allowed_channels: list[Any] = field(default_factory=list)
    has_dev_channels: bool = False
    session_project_dir: str | None = None
    prompt_cache_1h_allowlist: list[str] | None = None
    prompt_cache_1h_eligible: bool | None = None
    afk_mode_header_latched: bool | None = None
    fast_mode_header_latched: bool | None = None
    cache_editing_header_latched: bool | None = None
    thinking_clear_latched: bool | None = None
    prompt_id: str | None = None
    last_main_request_id: str | None = None
    last_api_completion_timestamp: float | None = None
    pending_post_compaction: bool = False


def _get_initial_state() -> State:
    # Resolve symlinks in cwd (mirrors state.ts getInitialState)
    raw_cwd = os.getcwd()
    try:
        resolved_cwd = str(Path(raw_cwd).resolve())
    except OSError:
        resolved_cwd = raw_cwd

    return State(
        original_cwd=resolved_cwd,
        project_root=resolved_cwd,
        cwd=resolved_cwd,
        start_time=time.time() * 1000,
        last_interaction_time=time.time() * 1000,
        session_id=as_session_id(str(_uuid_mod.uuid4())),
    )


# Module-level singleton
_STATE: State = _get_initial_state()


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def get_session_id() -> SessionId:
    return _STATE.session_id


def regenerate_session_id(set_current_as_parent: bool = False) -> SessionId:
    if set_current_as_parent:
        _STATE.parent_session_id = _STATE.session_id
    _STATE.plan_slug_cache.pop(_STATE.session_id, None)
    new_id = as_session_id(str(_uuid_mod.uuid4()))
    _STATE.session_id = new_id
    _STATE.session_project_dir = None
    return new_id


def get_parent_session_id() -> SessionId | None:
    return _STATE.parent_session_id


def switch_session(session_id: SessionId, project_dir: str | None = None) -> None:
    _STATE.plan_slug_cache.pop(_STATE.session_id, None)
    _STATE.session_id = session_id
    _STATE.session_project_dir = project_dir
    session_switched.emit(session_id)


def get_original_cwd() -> str:
    return _STATE.original_cwd


def get_project_root() -> str:
    return _STATE.project_root


def get_cwd_state() -> str:
    return _STATE.cwd


def set_cwd(new_cwd: str) -> None:
    _STATE.cwd = new_cwd
    cwd_state_changed.emit(new_cwd)


def get_session_trust_accepted() -> bool:
    return _STATE.session_trust_accepted


def set_session_trust_accepted(value: bool) -> None:
    _STATE.session_trust_accepted = value


def get_state() -> State:
    """Return the mutable global state object."""
    return _STATE


def reset_state_for_tests() -> None:
    """Reset all state fields to initial values (test helper)."""
    global _STATE
    _STATE = _get_initial_state()


# ---------------------------------------------------------------------------
# Convenience updaters (mirrors TS pattern of direct field mutation)
# ---------------------------------------------------------------------------

def update_state(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        setattr(_STATE, key, value)
