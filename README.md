# OPTIMUS Mark I

> A complete, 1:1 Python port of [Claude Code](https://claude.ai/code) (TypeScript/Bun → Python 3.12+)
> Author: Ahmet Erol Bayrak

---

## What is this?

Claude Code is Anthropic's official agentic coding CLI — written in TypeScript/Bun with 1,332 source files. **OPTIMUS Mark I** is a forensic translation of that codebase into idiomatic Python. Same architecture, same abstractions, same behavior — expressed in Python.

This is not a reimagining. It is a port.

---

## Status

**~5% complete** — foundation layer done, agent loop and tools in progress.

See [`STATUS.md`](./STATUS.md) for a full breakdown of what's ported, what's next, and all design decisions.

---

## What's done

| Layer | Files |
|-------|-------|
| Types (message, ids, permissions, tools, hooks, logs) | 6 |
| Constants (common, tools, OAuth) | 3 |
| Bootstrap state singleton | 1 |
| Config system (GlobalConfig 100+ fields, file locking) | 2 |
| Environment & feature detection | 4 |
| CWD, path, debug, git utilities | 7 |
| Messages, session storage, paste store, history | 5 |
| Shell utilities (bash parser, quoting, pipe rearrangement) | 6 |
| **Permissions system (all 24 files)** | 24 |
| Tool Protocol + registry | 2 |

---

## Technology Stack

| TypeScript | Python |
|-----------|--------|
| Bun runtime | Python 3.12+ |
| TypeScript strict | `typing` + `mypy --strict` |
| React + Ink | Textual |
| Zod | Pydantic v2 |
| Commander.js | Click |
| `@anthropic-ai/sdk` | `anthropic` Python SDK |
| `@modelcontextprotocol/sdk` | `mcp` Python SDK |
| `EventEmitter` | `pyee.AsyncIOEventEmitter` |
| `chalk` | `rich` |

---

## Project Structure

```
optimus/
├── bootstrap/state.py        # Global session state singleton
├── constants/                # common, tools, oauth
├── types/                    # message, ids, permissions, tools, hooks, logs
├── history.py                # Async buffered prompt history
├── tool.py                   # Tool Protocol + ToolUseContext
├── tools.py                  # Tool registry
└── utils/
    ├── config.py             # GlobalConfig (1,800+ lines)
    ├── permissions/          # Full permissions system (24 files)
    ├── bash/                 # Shell parsing & quoting
    ├── shell/                # ShellProvider Protocol
    └── ...                   # env, cwd, path, debug, git, messages, ...
```

---

## Roadmap

1. **Shell execution** — `BashProvider` async subprocess runner
2. **BashTool** — first runnable tool
3. **Query engine** — agent loop (streaming API, tool dispatch)
4. **Remaining 39 tools** — FileRead, FileEdit, Glob, Grep, Agent, MCP, ...
5. **Services** — Anthropic API client, MCP server management
6. **CLI entry point** — `optimus` command via Click
7. **TUI** — Textual app replacing React/Ink

---

*OPTIMUS Mark I — Python port of Claude Code*
