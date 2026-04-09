# OPTIMUS Mark I

> A fully autonomous Python-native agentic coding engine.
> Author: Ahmet Erol Bayrak

---

## What is this?

OPTIMUS Mark I is a Python 3.12+ agentic coding assistant — an autonomous engine that can read, write, and reason about code, execute shell commands, manage files, and collaborate with external services via MCP.

Built entirely in Python with a Textual TUI, async-first architecture, and a complete permission/safety system.

---

## Status

**Foundation layer complete — agent loop and tools in progress.**

See [`STATUS.md`](./STATUS.md) for the full breakdown.

---

## What's built

| Layer | Files |
|-------|-------|
| Types (message, ids, permissions, tools, hooks, logs) | 6 |
| Constants (common, tools, OAuth) | 3 |
| Bootstrap state singleton | 1 |
| Config system (100+ fields, file locking, mtime cache) | 2 |
| Environment & feature detection | 4 |
| CWD, path, debug, git utilities | 7 |
| Messages, session storage, paste store, history | 5 |
| Shell utilities (bash parser, quoting, pipe rearrangement) | 6 |
| **Permissions system (24 modules)** | 24 |
| Tool Protocol + registry | 2 |

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
    ├── permissions/          # Full permissions system (24 modules)
    ├── bash/                 # Shell parsing & quoting
    ├── shell/                # ShellProvider Protocol
    └── ...                   # env, cwd, path, debug, git, messages, ...
```

---

## Roadmap

1. **Shell execution** — `BashProvider` async subprocess runner
2. **BashTool** — first runnable tool
3. **Query engine** — agent loop (streaming API, tool dispatch)
4. **Remaining tools** — FileRead, FileEdit, Glob, Grep, Agent, MCP, ...
5. **Services** — API client, MCP server management
6. **CLI entry point** — `optimus` command
7. **TUI** — Textual app

---

*OPTIMUS Mark I — autonomous Python coding agent*
