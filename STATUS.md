# OPTIMUS Mark I — Porting Status

> Author: Ahmet Erol Bayrak
> Last updated: 2026-04-10

---

## Overview

| Metric | Value |
|--------|-------|
| Target TS source files | 1,332 |
| Python files created | 163 (incl. `__init__.py`) / 112 substantive |
| Total Python lines | ~22,800 |
| Completion (file count) | ~8% |

**Current focus:** BashTool security subsystem. Four major files just ported (heredoc, commands, bash_security, bash_permissions). Next: remaining BashTool sub-modules (pathValidation, readOnlyValidation, sedValidation, bashCommandHelpers, modeValidation), then fix the known thin files below.

---

## ⚠️ Known Thin / Incomplete Files (Must Fix)

These files exist but are **not genuine 1:1 ports**. They must be treated as blockers.

| File | Python lines | TS source lines | Status |
|------|-------------|-----------------|--------|
| `tools/bash_tool/bash_tool.py` | 163 | ~800 (BashTool.ts) | ❌ Skeleton |
| `services/mcp.py` | 82 | ~12,238 (24 TS files in services/mcp/) | ❌ Stub — entire MCP client missing |
| `utils/permissions/bypass_permissions_killswitch.py` | 124 | — | ⚠️ Has `pass` stubs in gate checks |
| `utils/permissions/permission_setup.py` | 601 | — | ⚠️ Some hooks not wired |
| `utils/permissions/permission_update.py` | — | — | ⚠️ Persistence logic incomplete |
| `utils/permissions/permissions_loader.py` | — | — | ⚠️ File I/O partially stubbed |

---

## What's Done ✅

### Types (`optimus/types/`)
- `ids.py` — typed ID wrappers (SessionId, ToolUseId, etc.)
- `message.py` — all message variants (UserMessage, AssistantMessage, ToolUseBlock, etc.)
- `permissions.py` — full permission rule, result, and context types (372 lines)
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
- `env_utils.py` — `is_env_truthy`, `get_claude_config_home_dir`
- `features.py` — feature flag evaluation
- `env.py` — terminal + deployment environment detection (351 lines)
- `cwd.py` — `ContextVar`-based per-task CWD override (mirrors `AsyncLocalStorage`)
- `path.py` — path expansion, sanitization, traversal detection, djb2 hash
- `config.py` — `GlobalConfig` (100+ fields), `ProjectConfig`, mtime-based cache, cross-platform file locking, camelCase↔snake_case JSON (1,806 lines)
- `config_constants.py` — notification channels, editor modes, teammate modes
- `debug_filter.py` — debug category parsing and filtering
- `debug.py` — timestamped debug logging to `~/.optimus/debug/<session>.txt`
- `git.py` — git root detection + canonical worktree resolution
- `messages.py` — message factory functions, `normalize_messages`, `derive_uuid` (630 lines)
- `session_storage_portable.py` — compact-boundary transcript reader, `sanitize_path` (486 lines)
- `get_worktree_paths_portable.py` — async git worktree path detection
- `paste_store.py` — content-addressable paste cache
- `shell_config.py` — shell rcfile detection (zsh, bash, fish)

### Shell Utilities (`optimus/utils/bash/`)
- `bash_parser.py` — bash command tokenizer (607 lines — ⚠️ partial vs 4,436-line TS original)
- `bash_pipe_command.py` — pipe rearrangement for safe stdin redirect
- `shell_quote.py` — shell quoting/unquoting, `try_parse_shell_command` (317 lines)
- `shell_quoting.py` — `quote_shell_command`, Windows null redirect rewrite
- `shell_prefix.py` — shell prefix detection (sudo, env var assignments)
- **`heredoc.py`** ✅ NEW — full heredoc extraction/restoration with PST_EOFTOKEN protection, incremental O(n) scanner, nested-heredoc filtering (406 lines, port of 733-line `heredoc.ts`)
- **`commands.py`** ✅ NEW — `split_command_DEPRECATED`, `extract_output_redirections`, `is_help_command`, salted placeholders, FAIL-CLOSED on parse error (520 lines, port of 1,339-line `commands.ts`)

### Shell Provider (`optimus/utils/shell/`)
- `shell_provider.py` — `ShellProvider` Protocol
- `bash_provider.py` — async subprocess, output truncation (100KB), cwd tracking
- `shell_tool_utils.py` — PowerShell gate

### Permissions System (`optimus/utils/permissions/`) — 24 modules

| Module | Lines | Notes |
|--------|-------|-------|
| `permission_mode.py` | — | Mode enum |
| `permission_result.py` | — | `PermissionResult` variants |
| `permission_rule.py` | — | `PermissionRule` model |
| `permission_update.py` | — | `apply_permission_updates` ⚠️ persistence incomplete |
| `permission_update_schema.py` | — | Discriminated union, 6 update types |
| `permission_prompt_tool_result_schema.py` | — | Tool result schema |
| `classifier_shared.py` | — | `parse_classifier_response` |
| `classifier_decision.py` | — | Auto-mode allowlist |
| `dangerous_patterns.py` | — | Dangerous bash patterns |
| `bash_classifier.py` | — | Stub (classifier is ant-only/feature-gated) |
| `yolo_classifier.py` | — | Auto-mode YOLO classifier |
| `shell_rule_matching.py` | — | Wildcard/prefix/exact matching |
| `path_validation.py` | 331 | Path safety validation |
| `filesystem.py` | 718 | `matching_rule_for_input`, path-in-working-path |
| `permission_rule_parser.py` | — | Full escape/unescape/parse/serialize |
| `permission_explainer.py` | — | AI-powered permission explanation |
| `auto_mode_state.py` | — | Module-level flags for auto mode |
| `bypass_permissions_killswitch.py` | 124 | ⚠️ Gate checks have `pass` stubs |
| `denial_tracking.py` | — | `DenialTrackingState` |
| `get_next_permission_mode.py` | — | `cycle_permission_mode` |
| `shadowed_rule_detection.py` | — | Unreachable rule detection |
| `permissions_loader.py` | — | ⚠️ File I/O partially stubbed |
| `permission_setup.py` | 601 | ⚠️ Some hooks not fully wired |
| `permissions.py` | 542 | Core permission gate |

### Tool Infrastructure
- `history.py` — async buffered prompt history, file locking, pasted-text ref expansion (457 lines)
- `tool.py` — `Tool` Protocol, `ToolUseContext`, `build_tool` factory (467 lines)
- `tools.py` — full tool registry + `get_all_tools()` (512 lines)

### Query Engine
- `query.py` — streaming agentic loop (API call → tool dispatch → multi-turn)

### Commands
- `commands/__init__.py` — `PromptCommand` dataclass, `find_command`, `get_commands`

### Swarm Utilities
- `utils/swarm/mailbox.py` — agent mailbox (per-agent async queues)
- `utils/swarm/team_helpers.py` — team file helpers

### Task Registry
- `tasks/task_registry.py` — background asyncio task handles
- `utils/tasks.py` — in-memory task store (create/get/update/delete/list)

### Services
- `services/mcp.py` — ❌ **82-line stub** (real MCP client is 12,238 TS lines across 24 files — not ported)

### BashTool (`optimus/tools/bash_tool/`)
- `bash_tool.py` — ❌ **163-line skeleton** (needs full port of BashTool.ts)
- **`bash_security.py`** ✅ NEW — all 23 validators, `ValidationContext`, misparsing gate, deferred-validator ordering (834 lines, port of 2,592-line `bashSecurity.ts`)
- **`bash_permissions.py`** ✅ NEW — full 17-step `bash_tool_has_permission` decision flow, `strip_safe_wrappers`, `strip_all_leading_env_vars`, `strip_wrappers_from_argv`, `get_simple_command_prefix`, speculative classifier lifecycle, cd+git compound check (1,967 lines, port of 2,621-line `bashPermissions.ts`)

### Tools (40 total — ⚠️ depth varies)

> Many tools below were written in an earlier session before the 1:1 discipline was enforced.
> Tools marked ⚠️ need an audit pass against their TS originals.

| Tool | File | Notes |
|------|------|-------|
| BashTool | `bash_tool/bash_tool.py` | ❌ Skeleton — needs full port |
| Read | `file_read_tool/` | ⚠️ Needs audit |
| Edit | `file_edit_tool/` | ⚠️ Needs audit |
| Write | `file_write_tool/` | ⚠️ Needs audit |
| Glob | `glob_tool/` | ⚠️ Needs audit |
| Grep | `grep_tool/` | ⚠️ Needs audit |
| LS | `ls_tool/` | ⚠️ Needs audit |
| WebFetch | `web_fetch_tool/` | ⚠️ Needs audit |
| WebSearch | `web_search_tool/` | ⚠️ Needs audit |
| TodoWrite | `todo_write_tool/` | ⚠️ Needs audit |
| Agent | `agent_tool/` | ⚠️ Needs audit |
| TaskCreate/Get/Update/List/Stop/Output | `task_*_tool/` | ⚠️ Needs audit |
| TeamCreate/Delete | `team_*_tool/` | ⚠️ Needs audit |
| CronCreate/Delete/List | `schedule_cron_tool/` | ⚠️ Needs audit |
| SendMessage | `send_message_tool/` | ⚠️ Needs audit |
| RemoteTrigger | `remote_trigger_tool/` | ⚠️ Needs audit |
| EnterWorktree/ExitWorktree | `*_worktree_tool/` | ⚠️ Needs audit |
| MCP resources | `list_mcp_resources_tool/`, `read_mcp_resource_tool/` | ⚠️ Needs audit |
| Brief | `brief_tool/` | ⚠️ Needs audit |
| Config | `config_tool/` | ⚠️ Needs audit |
| ToolSearch | `tool_search_tool/` | ⚠️ Needs audit |
| REPL | `repl_tool/` | ⚠️ Needs audit |
| PowerShell | `powershell_tool/` | ⚠️ Needs audit |
| Skill | `skill_tool/` | ⚠️ Needs audit |
| SyntheticOutput | `synthetic_output_tool/` | ⚠️ Needs audit |
| McpTool | `mcp_tool/` | ⚠️ Needs audit |
| McpAuth | `mcp_auth_tool/` | ⚠️ Needs audit |
| LSP | `lsp_tool/` | ⚠️ Placeholder only |
| AskUserQuestion | `ask_user_question_tool/` | ⚠️ Needs audit |
| NotebookEdit | `notebook_edit_tool/` | ⚠️ Needs audit |
| EnterPlanMode/ExitPlanMode | `*_plan_mode_tool/` | ⚠️ Needs audit |
| Sleep | `sleep_tool/` | ⚠️ Needs audit |

### CLI
- `__main__.py` — `python -m optimus` entry point (REPL + single-turn)

---

## What's Next 🔜

### Priority 1 — Complete BashTool (immediate blockers)
These are imported by `bash_permissions.py` via `try/except ImportError` — they must be ported for the tool to be functional.

| File to create | TS original | TS lines |
|----------------|-------------|----------|
| `bash_tool/bash_command_helpers.py` | `bashCommandHelpers.ts` | 265 |
| `bash_tool/mode_validation.py` | `modeValidation.ts` | 115 |
| `bash_tool/path_validation.py` | `pathValidation.ts` | 1,303 |
| `bash_tool/read_only_validation.py` | `readOnlyValidation.ts` | 1,990 |
| `bash_tool/sed_edit_parser.py` | `sedEditParser.ts` | 322 |
| `bash_tool/sed_validation.py` | `sedValidation.ts` | 684 |
| `bash_tool/should_use_sandbox.py` | `shouldUseSandbox.ts` | 153 |
| `bash_tool/command_semantics.py` | `commandSemantics.ts` | 140 |
| `bash_tool/bash_tool.py` (rewrite) | `BashTool.ts` | ~800 |

### Priority 2 — Fix Known Thin Files
- `services/mcp.py` → full port of 24 TS files in `services/mcp/` (12,238 lines total)
- `tools/bash_tool/bash_tool.py` → rewrite from skeleton
- `utils/permissions/bypass_permissions_killswitch.py` → implement gate checks
- `utils/permissions/permissions_loader.py` → implement file I/O
- `utils/bash/bash_parser.py` → complete vs 4,436-line TS original

### Priority 3 — Audit all 40 tools
Each tool needs line count comparison against its TS original. Any ratio worse than 1:8 is a red flag.

### Priority 4 — Remaining BashTool TS files
- `bash_tool/comment_label.py` (commentLabel.ts)
- `bash_tool/destructive_command_warning.py` (destructiveCommandWarning.ts)
- `bash_tool/prompt.py` (prompt.ts)
- `bash_tool/tool_name.py` (toolName.ts)
- `bash_tool/utils.py` (utils.ts)

### Priority 5 — utils/bash/ast.py
`bash_permissions.py` calls `parse_for_security_from_ast` and `check_semantics` — these live in `utils/bash/ast.ts` (not yet ported). Without them, tree-sitter AST path is always `parse-unavailable`.

### Priority 6 — Services layer
- `services/api/` — 18 TS files (API client, streaming, retries, token counting)
- `services/mcp/` — 24 TS files (full MCP client — stdio + SSE + auth + OAuth)
- `services/compact/` — 10 TS files (context compaction)
- `services/oauth/` — 5 TS files

### Priority 7 — CLI slash commands (~30+)

### Priority 8 — Textual TUI
- Full React/Ink → Textual translation (largest single chunk remaining)

### Priority 9 — Remaining utils (1,100+ modules)
All subdirectories under `src/utils/` not yet ported:
`git/`, `github/`, `teleport/`, `suggestions/`, `plugins/`, `sandbox/`, `platform/`, `windowsPaths/`, `array/`, `slowOperations/`, `errors/`, etc.

---

## Line-Count Audit Log

| Python file | Lines | TS original | TS lines | Ratio | Status |
|-------------|-------|-------------|----------|-------|--------|
| `bash_permissions.py` | 1,967 | `bashPermissions.ts` | 2,621 | 1:1.3 | ✅ |
| `bash_security.py` | 834 | `bashSecurity.ts` | 2,592 | 1:3.1 | ✅ |
| `utils/bash/commands.py` | 520 | `commands.ts` | 1,339 | 1:2.6 | ✅ |
| `utils/bash/heredoc.py` | 406 | `heredoc.ts` | 733 | 1:1.8 | ✅ |
| `utils/config.py` | 1,806 | `config.ts` | — | — | ✅ |
| `utils/permissions/filesystem.py` | 718 | `filesystem.ts` | 1,777 | 1:2.5 | ✅ |
| `utils/permissions/permissions.py` | 542 | `permissions.ts` | 1,486 | 1:2.7 | ✅ |
| `utils/bash/bash_parser.py` | 607 | `parser.ts` | 4,436 | 1:7.3 | ⚠️ Borderline |
| `tools/bash_tool/bash_tool.py` | 163 | `BashTool.ts` | ~800 | 1:4.9 | ❌ Skeleton |
| `services/mcp.py` | 82 | 24 TS files | 12,238 | 1:149 | ❌ Stub |

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
| `feature('FLAG')` → `False` constant | Bun DCE feature flags always off in Python port |
| `logEvent(...)` → no-op | Analytics telemetry omitted |
| `shlex` instead of `shell-quote` | Stricter (raises on unterminated quotes — safer) |
| `try/except ImportError` in bash_permissions | Defers unported sub-modules cleanly; documented in PORTING_NOTES.md |
