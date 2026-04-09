# OPTIMUS Mark I — Porting Status

> Python port of Claude Code (TypeScript/Bun) → Python 3.12+
> Author: Ahmet Erol Bayrak
> Last updated: 2026-04-09

---

## Overview

| Metric | Count |
|--------|-------|
| TypeScript source files | 1,332 |
| Python files ported | 63 |
| Completion | ~5% |

The foundation layer is solid. Core types, configuration, permissions, and shell utilities are all done. The remaining 95% is tools (40 tools), the agent query loop, services (MCP, API, analytics), and the Textual TUI.

---

## What's Done ✅

### Types (`optimus/types/`)
| Python | TypeScript |
|--------|-----------|
| `types/ids.py` | `types/ids.ts` |
| `types/message.py` | `types/message.ts` |
| `types/permissions.py` | `types/permissions.ts` |
| `types/tools.py` | `types/tools.ts` |
| `types/hooks.py` | `types/hooks.ts` |
| `types/logs.py` | `types/logs.ts` |

### Constants (`optimus/constants/`)
| Python | TypeScript |
|--------|-----------|
| `constants/common.py` | `constants/common.ts` |
| `constants/tools.py` | `constants/tools.ts` |
| `constants/oauth.py` | `constants/oauth.ts` |

### Bootstrap (`optimus/bootstrap/`)
| Python | TypeScript |
|--------|-----------|
| `bootstrap/state.py` | `bootstrap/state.ts` |

State singleton with 50+ fields, `switch_session()`, all getters/setters.

### Core Utilities (`optimus/utils/`)
| Python | TypeScript |
|--------|-----------|
| `utils/env_utils.py` | `utils/envUtils.ts` |
| `utils/features.py` | `utils/features.ts` |
| `utils/env.py` | `utils/env.ts` |
| `utils/cwd.py` | `utils/cwd.ts` |
| `utils/path.py` | `utils/path.ts` |
| `utils/config.py` | `utils/config.ts` |
| `utils/config_constants.py` | (extracted constants) |
| `utils/debug_filter.py` | `utils/debugFilter.ts` |
| `utils/debug.py` | `utils/debug.ts` |
| `utils/git.py` | `utils/git.ts` (root-finding + canonical resolution) |
| `utils/messages.py` | `utils/messages.ts` |
| `utils/session_storage_portable.py` | `utils/sessionStoragePortable.ts` |
| `utils/get_worktree_paths_portable.py` | `utils/getWorktreePathsPortable.ts` |
| `utils/paste_store.py` | `utils/pasteStore.ts` |
| `utils/shell_config.py` | `utils/shellConfig.ts` |

### Shell Utilities (`optimus/utils/bash/`, `optimus/utils/shell/`)
| Python | TypeScript |
|--------|-----------|
| `utils/bash/bash_parser.py` | `utils/bash/bashParser.ts` |
| `utils/bash/bash_pipe_command.py` | `utils/bash/bashPipeCommand.ts` |
| `utils/bash/shell_quote.py` | `utils/bash/shellQuote.ts` |
| `utils/bash/shell_quoting.py` | `utils/bash/shellQuoting.ts` |
| `utils/bash/shell_prefix.py` | `utils/bash/shellPrefix.ts` |
| `utils/shell/shell_provider.py` | `utils/shell/shellProvider.ts` |

### Permissions System (`optimus/utils/permissions/`) — 24 files
Full port of every file in `src/utils/permissions/`:

| Python | TypeScript |
|--------|-----------|
| `permission_mode.py` | `PermissionMode.ts` |
| `permission_result.py` | `PermissionResult.ts` |
| `permission_rule.py` | `PermissionRule.ts` |
| `permission_update.py` | `PermissionUpdate.ts` |
| `permission_update_schema.py` | `PermissionUpdateSchema.ts` |
| `permission_prompt_tool_result_schema.py` | `PermissionPromptToolResultSchema.ts` |
| `classifier_shared.py` | `classifierShared.ts` |
| `classifier_decision.py` | `classifierDecision.ts` |
| `dangerous_patterns.py` | `dangerousPatterns.ts` |
| `bash_classifier.py` | `bashClassifier.ts` |
| `yolo_classifier.py` | `yoloClassifier.ts` |
| `shell_rule_matching.py` | `shellRuleMatching.ts` |
| `path_validation.py` | `pathValidation.ts` |
| `filesystem.py` | `filesystem.ts` |
| `permission_rule_parser.py` | `permissionRuleParser.ts` |
| `permission_explainer.py` | `permissionExplainer.ts` |
| `auto_mode_state.py` | `autoModeState.ts` |
| `bypass_permissions_killswitch.py` | `bypassPermissionsKillswitch.ts` |
| `denial_tracking.py` | `denialTracking.ts` |
| `get_next_permission_mode.py` | `getNextPermissionMode.ts` |
| `shadowed_rule_detection.py` | `shadowedRuleDetection.ts` |
| `permissions_loader.py` | `permissionsLoader.ts` |
| `permission_setup.py` | `permissionSetup.ts` |
| `permissions.py` | `permissions.ts` |

### History & Tool Infrastructure
| Python | TypeScript |
|--------|-----------|
| `history.py` | `history.ts` |
| `tool.py` | `tool.ts` |
| `tools.py` | `tools.ts` |

---

## What's Next 🔜

### Priority 1 — Shell Execution (needed by BashTool)
- `utils/shell/bash_provider.py` — BashProvider implementation (async subprocess, streaming stdout/stderr, timeout, output truncation)
- `utils/shell/shell_tool_utils.py` — shared shell tool utilities

### Priority 2 — BashTool (first runnable tool)
- `tools/bash_tool/bash_command_helpers.py`
- `tools/bash_tool/bash_permissions.py`
- `tools/bash_tool/bash_security.py`
- `tools/bash_tool/bash_tool.py` — full BashTool implementing `Tool` Protocol

### Priority 3 — Agent Query Loop (makes the agent actually run)
- `query_engine.py` — streaming API call loop, tool dispatch
- `query.py` — top-level `query()` function, abort handling

### Priority 4 — Remaining 39 Tools
In dependency order:
1. `FileReadTool` (`Read` in TS)
2. `FileEditTool` (`Edit` in TS)
3. `FileWriteTool` (`Write` in TS)
4. `GlobTool`
5. `GrepTool`
6. `LSTool`
7. `AgentTool`
8. `MCPTool`
9. ... (31 more)

### Priority 5 — Services
- `services/api.py` — Anthropic API client wrapper (streaming, retries, token counting)
- `services/mcp.py` — MCP server management (stdio + SSE transports)
- `services/analytics.py` — telemetry/statsig integration

### Priority 6 — CLI Entry Point
- `__main__.py` — `optimus` CLI (Click), argument parsing, REPL loop
- Slash commands (30+ commands)

### Priority 7 — TUI
- Textual app replacing React/Ink
- All UI components (prompt, diff viewer, tool output, status bar)

### Priority 8 — Remaining Utils (~1,250 TypeScript files)
Large swaths still unported:
- `utils/git/` subdirectory (gitFilesystem, gitignore, gitConfigParser)
- `utils/github/`
- `utils/teleport/`
- `utils/suggestions/`
- `utils/plugins/`
- Many individual utility files

---

## Key Design Decisions (Deviations from TypeScript)

| Decision | Reason |
|----------|--------|
| `contextvars.ContextVar` instead of `AsyncLocalStorage` | Python's asyncio equivalent for per-task CWD override |
| `fcntl.flock` / `msvcrt.locking` for file locking | Cross-platform advisory locks (no `proper-lockfile` npm package) |
| Explicit camelCase↔snake_case dicts in `config.py` | JSON serialization roundtrip without runtime reflection |
| `fnmatch` instead of `ignore` npm package | gitignore-style glob matching |
| `asyncio.create_subprocess_exec` instead of `execa` | Native Python async subprocess |
| `pyee.AsyncIOEventEmitter` instead of Node EventEmitter | Async-compatible event emitter |
| `lru_cache` instead of lodash `memoize` | Standard library, same semantics |

---

## Project Structure

```
optimus/
├── __init__.py
├── tool.py                  # Tool Protocol + ToolUseContext
├── tools.py                 # Tool registry
├── history.py               # Prompt history (async buffered writes)
├── bootstrap/
│   └── state.py             # Global session state singleton
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
    ├── config.py            # GlobalConfig + ProjectConfig (1,806 lines)
    ├── cwd.py               # ContextVar-based CWD override
    ├── debug.py             # Debug logging
    ├── debug_filter.py      # Debug category filtering
    ├── env.py               # Environment detection
    ├── env_utils.py         # Low-level env helpers
    ├── features.py          # Feature flags
    ├── git.py               # Git root detection
    ├── get_worktree_paths_portable.py
    ├── messages.py          # Message factory functions
    ├── paste_store.py       # Content-addressable paste storage
    ├── path.py              # Path utilities
    ├── session_storage_portable.py
    ├── shell_config.py
    ├── bash/
    │   ├── bash_parser.py
    │   ├── bash_pipe_command.py
    │   ├── shell_prefix.py
    │   ├── shell_quote.py
    │   └── shell_quoting.py
    ├── permissions/         # 24 files — full permissions system
    │   └── ...
    └── shell/
        └── shell_provider.py
```

---

## Technology Stack

| TypeScript | Python |
|-----------|--------|
| Bun runtime | Python 3.12+ |
| TypeScript strict types | `typing` + `mypy --strict` |
| React + Ink | Textual |
| Zod | Pydantic v2 |
| Commander.js | Click |
| `@anthropic-ai/sdk` | `anthropic` Python SDK |
| `@modelcontextprotocol/sdk` | `mcp` Python SDK |
| `EventEmitter` | `pyee.AsyncIOEventEmitter` |
| `chalk` | `rich` |

---

*OPTIMUS Mark I — Python port of Claude Code*
*https://github.com/spedatox/speda-mark6*
