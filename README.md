# OPTIMUS Mark I

> A fully autonomous Python-native agentic coding engine.
> Author: Ahmet Erol Bayrak

---

## What is this?

OPTIMUS Mark I is a **complete, 1:1 Python port** of Claude Code — the TypeScript/Bun agentic coding assistant. Same architecture, same abstractions, same security model, same capabilities — expressed idiomatically in Python 3.12+.

It can read, write, and reason about code, execute shell commands, manage files, and collaborate with external services via MCP.

---

## Status

**~8% ported (112 substantive files / 1,332 target). Bash security subsystem just completed.**

Four major bash security files landed this session. Remaining focus: complete BashTool sub-modules, fix known thin files (MCP client, bash_tool.py), audit all 40 tools.

See [`STATUS.md`](./STATUS.md) for the full breakdown including known thin/incomplete files.

---

## What's Built

| Layer | Files | Lines | Notes |
|-------|-------|-------|-------|
| Types (message, ids, permissions, tools, hooks, logs) | 6 | ~1,400 | ✅ Complete |
| Constants (common, tools, OAuth) | 3 | ~300 | ✅ Complete |
| Bootstrap state singleton | 1 | ~400 | ✅ Complete |
| Config system (100+ fields, file locking, mtime cache) | 2 | ~1,900 | ✅ Complete |
| Environment & feature detection | 4 | ~500 | ✅ Complete |
| CWD, path, debug, git utilities | 7 | ~600 | ✅ Complete |
| Messages, session storage, paste store, history | 5 | ~1,600 | ✅ Complete |
| Shell utilities (bash parser, quoting, pipe, prefix) | 5 | ~1,700 | ⚠️ bash_parser partial |
| **Heredoc extraction** (NEW) | 1 | 406 | ✅ Full port of heredoc.ts |
| **Bash command splitting** (NEW) | 1 | 520 | ✅ Full port of commands.ts |
| Permissions system | 24 | ~5,000 | ⚠️ Some stubs remain |
| Tool Protocol + registry | 2 | ~980 | ✅ Complete |
| Query engine (streaming agent loop) | 1 | — | ✅ Complete |
| **Bash security validators** (NEW) | 1 | 834 | ✅ Full port of bashSecurity.ts (all 23 validators) |
| **Bash permissions orchestration** (NEW) | 1 | 1,967 | ✅ Full port of bashPermissions.ts (17-step flow) |
| Tools (40 total) | 40 | ~3,000 | ⚠️ Depth varies — see STATUS.md |
| Services/MCP | 1 | 82 | ❌ Stub — 24 TS files not yet ported |
| Swarm, tasks, commands | 5 | ~400 | ⚠️ Partial |
| CLI entry point | 1 | — | ⚠️ Basic only |

---

## Technology Stack

| Concern | Library |
|---------|---------|
| Runtime | Python 3.12+ |
| Type safety | `typing` + `mypy --strict` |
| TUI | Textual |
| Schema validation | Pydantic v2 |
| CLI | Click |
| LLM API | `anthropic` Python SDK |
| MCP | `mcp` Python SDK |
| Events | `pyee.AsyncIOEventEmitter` |
| Output | `rich` |
| Async subprocess | `asyncio.create_subprocess_exec` |

---

## Project Structure

```
optimus/
├── __main__.py               # CLI entry point
├── tool.py                   # Tool Protocol + ToolUseContext
├── tools.py                  # Tool registry (40 tools)
├── history.py                # Async buffered prompt history
├── query.py                  # Streaming agent loop
├── bootstrap/
│   └── state.py              # Global session state singleton
├── commands/
│   └── __init__.py           # Slash command registry
├── constants/                # common, tools, oauth
├── services/
│   └── mcp.py                # ❌ Stub — MCP client not yet ported
├── tasks/
│   └── task_registry.py      # Background asyncio task handles
├── types/                    # message, ids, permissions, tools, hooks, logs
├── tools/
│   ├── bash_tool/
│   │   ├── bash_tool.py      # ❌ Skeleton — needs full port
│   │   ├── bash_security.py  # ✅ All 23 validators (port of bashSecurity.ts)
│   │   └── bash_permissions.py # ✅ Full permission flow (port of bashPermissions.ts)
│   └── ...                   # 39 other tools (depth varies)
└── utils/
    ├── config.py             # GlobalConfig (1,806 lines)
    ├── bash/
    │   ├── bash_parser.py    # ⚠️ Partial (607 / 4,436 TS lines)
    │   ├── commands.py       # ✅ split_command, extract_redirections
    │   ├── heredoc.py        # ✅ Full heredoc extraction/restoration
    │   ├── shell_quote.py    # ✅ try_parse_shell_command
    │   └── ...
    ├── permissions/          # 24 modules (⚠️ some stubs remain)
    ├── shell/                # BashProvider, ShellProvider Protocol
    └── ...                   # env, cwd, path, debug, git, messages, ...
```

---

## Porting Discipline

Every file is a **forensic translation** of its TypeScript original:

- Read the entire TS source before writing a single Python line
- Every exported function → Python equivalent with real logic
- Every constant, enum, type alias → ported
- Line count ratio checked: must be ≥ 1 Python line per 5 TS lines
- Any file with ratio worse than 1:8 is flagged as incomplete
- Deviations documented in `PORTING_NOTES.md`

---

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 1 | Bash security subsystem (heredoc, commands, bashSecurity, bashPermissions) | ✅ Done |
| 2 | Remaining BashTool files (pathValidation, readOnlyValidation, sedValidation, bashCommandHelpers, modeValidation, commandSemantics, shouldUseSandbox) | 🔜 Next |
| 3 | Fix bash_tool.py skeleton + MCP stub | 🔜 Next |
| 4 | Audit + fix all 40 tools | Pending |
| 5 | services/api/ (18 files) | Pending |
| 6 | services/mcp/ (24 files — full MCP client) | Pending |
| 7 | CLI slash commands (30+) | Pending |
| 8 | Textual TUI | Pending |
| 9 | Remaining utils (1,100+ modules) | Pending |

---

*OPTIMUS Mark I — autonomous Python coding agent*
*1:1 port of Claude Code by Ahmet Erol Bayrak*
