# OPTIMUS Mark I — Porting Status

> Author: Ahmet Erol Bayrak
> Last updated: 2026-04-09

---

## Overview

| Metric | Count |
|--------|-------|
| Target modules | ~1,300 |
| Python files completed | ~130 |
| Completion | ~10% |

Foundation + full tool set (40 tools) + query loop done. All 40 tools have Python implementations including TaskCreate/Get/Update/List, Cron (Create/Delete/List), Team (Create/Delete), SendMessage, RemoteTrigger, WorktreeEnter/Exit, MCP resources, Brief, Config, ToolSearch, REPL, PowerShell, Skill, SyntheticOutput, LSP, McpAuth. Supporting modules: task_registry, utils/tasks, services/mcp, utils/swarm, commands. Remaining: MCP full client implementation, Textual TUI, services/api, and the long tail of utilities.

---

## What's Done ✅

### Types (`optimus/types/`)
- `ids.py` — typed ID wrappers (SessionId, ToolUseId, etc.)
- `message.py` — all message variants (UserMessage, AssistantMessage, ToolUseBlock, etc.)
- `permissions.py` — permission rule and result types
- `tools.py` — tool input/output types
- `hooks.py` — hook event types
- `logs.py` — log entry types

### Constants (`optimus/constants/`)
- `common.py` — shared constants
- `tools.py` — tool-related constants
- `oauth.py` — OAuth config, scopes, URLs (prod/staging/local)

### Bootstrap (`optimus/bootstrap/`)
- `state.py` — global session state singleton (50+ fields), `switch_session()`, all getters/setters

### Core Utilities (`optimus/utils/`)
- `env_utils.py` — low-level env helpers (`is_env_truthy`, `get_claude_config_home_dir`)
- `features.py` — feature flag evaluation
- `env.py` — terminal + deployment environment detection
- `cwd.py` — `ContextVar`-based per-task CWD override (mirrors `AsyncLocalStorage`)
- `path.py` — path expansion, sanitization, traversal detection, djb2 hash
- `config.py` — `GlobalConfig` (100+ fields), `ProjectConfig`, mtime-based cache, cross-platform file locking, camelCase↔snake_case JSON serialization
- `config_constants.py` — notification channels, editor modes, teammate modes
- `debug_filter.py` — debug category parsing and filtering
- `debug.py` — timestamped debug logging to `~/.optimus/debug/<session>.txt`
- `git.py` — git root detection + canonical worktree resolution
- `messages.py` — message factory functions, `normalize_messages`, `derive_uuid`
- `session_storage_portable.py` — compact-boundary transcript reader, `sanitize_path`
- `get_worktree_paths_portable.py` — async git worktree path detection
- `paste_store.py` — content-addressable paste cache (`~/.optimus/paste-cache/`)
- `shell_config.py` — shell rcfile detection (zsh, bash, fish)

### Shell Utilities (`optimus/utils/bash/`, `optimus/utils/shell/`)
- `bash/bash_parser.py` — bash command tokenizer
- `bash/bash_pipe_command.py` — pipe rearrangement for safe stdin redirect
- `bash/shell_quote.py` — shell quoting / unquoting
- `bash/shell_quoting.py` — `quoteShellCommand`, Windows null redirect rewrite
- `bash/shell_prefix.py` — shell prefix detection (sudo, env var assignments)
- `shell/shell_provider.py` — `ShellProvider` Protocol (type, shellPath, buildExecCommand, getSpawnArgs)

### Permissions System (`optimus/utils/permissions/`) — 24 modules

| Module | Purpose |
|--------|---------|
| `permission_mode.py` | Mode enum: default / acceptEdits / bypassPermissions / plan / auto |
| `permission_result.py` | `PermissionResult` with behavior, message, decisionReason |
| `permission_rule.py` | `PermissionRule` Pydantic model |
| `permission_update.py` | `apply_permission_updates`, `persist_permission_updates` |
| `permission_update_schema.py` | Discriminated union for all 6 update types |
| `permission_prompt_tool_result_schema.py` | Tool result schema + decision extraction |
| `classifier_shared.py` | `extract_tool_use_block`, `parse_classifier_response` |
| `classifier_decision.py` | `SAFE_YOLO_ALLOWLISTED_TOOLS`, auto-mode allowlist |
| `dangerous_patterns.py` | Cross-platform code execution + dangerous bash patterns |
| `bash_classifier.py` | Bash command safety classifier |
| `yolo_classifier.py` | Auto-mode YOLO classifier |
| `shell_rule_matching.py` | Wildcard/prefix/exact rule matching with `\*` escape |
| `path_validation.py` | Path safety validation, dangerous removal detection |
| `filesystem.py` | `matching_rule_for_input`, `path_in_working_path`, temp dir handling |
| `permission_rule_parser.py` | Full escape/unescape/parse/serialize roundtrip |
| `permission_explainer.py` | AI-powered permission explanation |
| `auto_mode_state.py` | Module-level flags for auto mode |
| `bypass_permissions_killswitch.py` | Async gate checks for bypass mode |
| `denial_tracking.py` | `DenialTrackingState`, fallback-to-prompting logic |
| `get_next_permission_mode.py` | `get_next_permission_mode`, `cycle_permission_mode` |
| `shadowed_rule_detection.py` | Unreachable rule detection |
| `permissions_loader.py` | Load / add / delete rules from settings files |
| `permission_setup.py` | Dangerous-permission detection, `transition_permission_mode` |
| `permissions.py` | Core: `has_permissions_to_use_tool`, `check_permission`, `get_allow/deny/ask_rules` |

### History & Tool Infrastructure
- `history.py` — async buffered prompt history, file locking, pasted-text ref expansion
- `tool.py` — `Tool` Protocol, `ToolUseContext`, `build_tool` factory
- `tools.py` — full tool registry + `get_all_tools()`

### Shell Layer
- `utils/shell/bash_provider.py` — async subprocess, output truncation (100KB), cwd tracking
- `utils/shell/shell_tool_utils.py` — PowerShell gate
- `utils/bash/` — bash_parser, bash_pipe_command, shell_quote, shell_quoting, shell_prefix

### Query Engine
- `query.py` — streaming agentic loop (API call → tool dispatch → multi-turn)

### Tools
| Tool | Class |
|------|-------|
| `Bash` | `tools/bash_tool/bash_tool.py` |
| `Read` | `tools/file_read_tool/file_read_tool.py` |
| `Edit` | `tools/file_edit_tool/file_edit_tool.py` |
| `Write` | `tools/file_write_tool/file_write_tool.py` |
| `Glob` | `tools/glob_tool/glob_tool.py` |
| `Grep` | `tools/grep_tool/grep_tool.py` |
| `LS` | `tools/ls_tool/ls_tool.py` |
| `WebFetch` | `tools/web_fetch_tool/web_fetch_tool.py` |
| `WebSearch` | `tools/web_search_tool/web_search_tool.py` |
| `TodoWrite` | `tools/todo_write_tool/todo_write_tool.py` |
| `Agent` | `tools/agent_tool/agent_tool.py` |

### CLI Entry Point
- `__main__.py` — `python -m optimus` / `optimus` CLI (REPL + single-turn)

---

## What's Next 🔜

### Priority 1 — Remaining Tools (~29 tools)

### Priority 2 — BashTool (first runnable tool)
- `tools/bash_tool/bash_command_helpers.py`
- `tools/bash_tool/bash_permissions.py`
- `tools/bash_tool/bash_security.py`
- `tools/bash_tool/bash_tool.py`

### Priority 3 — Agent Query Loop
- `query_engine.py` — streaming API call loop, tool dispatch, abort handling
- `query.py` — top-level `query()` entry point

### Priority 4 — Remaining Tools (~40 total)
1. FileReadTool
2. FileEditTool
3. FileWriteTool
4. GlobTool
5. GrepTool
6. LSTool
7. AgentTool
8. MCPTool
9. ... (32 more)

### Priority 5 — Services
- `services/api.py` — API client (streaming, retries, token counting)
- `services/mcp.py` — MCP server management (stdio + SSE)
- `services/analytics.py` — telemetry

### Priority 6 — CLI Entry Point
- `__main__.py` — `optimus` CLI (Click), argument parsing, REPL loop
- 30+ slash commands

### Priority 7 — TUI
- Textual app
- Prompt, diff viewer, tool output, status bar components

### Priority 8 — Remaining Utilities (~1,250 modules)
- `utils/git/` — gitFilesystem, gitignore, gitConfigParser
- `utils/github/`
- `utils/teleport/`
- `utils/suggestions/`
- `utils/plugins/`

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| `contextvars.ContextVar` for CWD | Python's asyncio equivalent of `AsyncLocalStorage` |
| `fcntl.flock` / `msvcrt.locking` | Cross-platform advisory file locking |
| Explicit camelCase↔snake_case dicts | Safe JSON roundtrip without runtime reflection |
| `fnmatch` for gitignore-style matching | Replaces the `ignore` npm package |
| `asyncio.create_subprocess_exec` | Native async subprocess (replaces `execa`) |
| `lru_cache` instead of lodash `memoize` | Standard library, same semantics |
| Lazy imports inside functions | Avoids circular import chains |

---

## Project Structure

```
optimus/
├── __init__.py
├── tool.py
├── tools.py
├── history.py
├── bootstrap/
│   └── state.py
├── constants/
│   ├── common.py
│   ├── oauth.py
│   └── tools.py
├── types/
│   ├── ids.py
│   ├── message.py
│   ├── permissions.py
│   ├── tools.py
│   ├── hooks.py
│   └── logs.py
└── utils/
    ├── config.py
    ├── cwd.py
    ├── debug.py
    ├── debug_filter.py
    ├── env.py
    ├── env_utils.py
    ├── features.py
    ├── git.py
    ├── get_worktree_paths_portable.py
    ├── messages.py
    ├── paste_store.py
    ├── path.py
    ├── session_storage_portable.py
    ├── shell_config.py
    ├── bash/
    │   ├── bash_parser.py
    │   ├── bash_pipe_command.py
    │   ├── shell_prefix.py
    │   ├── shell_quote.py
    │   └── shell_quoting.py
    ├── permissions/
    │   └── (24 modules)
    └── shell/
        └── shell_provider.py
```
