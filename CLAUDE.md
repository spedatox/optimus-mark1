# OPTIMUS MARK I — CLAUDE.md

## Mission

Perform a **complete, 1:1, feature-identical Python port** of the Claude Code TypeScript/Bun codebase in `claude_code.zip`. The result is **OPTIMUS Mark I** — a fully autonomous Python-native agentic coding engine.

This is a forensic translation. Same architecture, same abstractions, same behavior, same capabilities — expressed idiomatically in Python. Not a rewrite. Not a reimagining. A port.

---

## How to Work

**The source is your specification.** Before implementing anything, extract and read the TypeScript source:

```bash
unzip claude_code.zip -d claude_code_src/
```

For every file you port:
1. Read the TypeScript source file completely
2. Understand what it does and how it fits into the system
3. Cross-reference with already-ported Python files for consistency
4. Then implement

When in doubt about any behavior, type, interface, or relationship — **go back to the source.** Do not guess. Do not infer from the filename alone. Read the file.

---

## Non-Negotiables

- **Every file gets ported.** If it exists in `src/`, it exists in `optimus/`. No exceptions.
- **No stubs.** A function with just `pass` is unacceptable. Every function must be fully implemented.
- **Read before write.** No implementing a module without reading its TypeScript source first.
- **Cross-reference constantly.** Before writing any module, check what already exists in the current `optimus/` codebase. Build on what's there. Stay consistent.
- **Idiomatic Python.** Translate intent, not syntax. Use `dataclasses`, `Protocol`, `TypedDict`, `asyncio`, `abc`, and `typing` as appropriate.
- **Test as you go.** After each module, write and run tests confirming behavioral equivalence with the TypeScript original.
- **Document deviations.** Any Python-specific adaptation or deliberate departure from the TypeScript source goes in `PORTING_NOTES.md` with justification.

---

## Technology Mapping

Resolve TypeScript dependencies to their Python equivalents:

| TypeScript | Python |
|---|---|
| Bun runtime | Python 3.12+ |
| TypeScript strict types | `typing` + `mypy --strict` |
| React + Ink | Textual |
| Zod | Pydantic v2 |
| Commander.js | Click or Typer |
| `@anthropic-ai/sdk` | `anthropic` Python SDK |
| `@modelcontextprotocol/sdk` | `mcp` Python SDK |
| `EventEmitter` | `pyee.AsyncIOEventEmitter` |
| `chalk` | `rich` |
| `async/await` | `asyncio` |
| `Promise.all` | `asyncio.gather` |
| `Map` / `Set` / `Record` | `dict` / `set` |
| `z.object({})` | Pydantic `BaseModel` |
| `index.ts` | `__init__.py` |
| `camelCase` files/functions | `snake_case` |

When you encounter a TypeScript dependency not in this table, find its Python equivalent yourself. There is always one.

---

## Structure

Mirror `src/` exactly as `optimus/`. Every subdirectory becomes a subpackage with `__init__.py`. Every `.ts` / `.tsx` file becomes a `.py` file with the name converted to `snake_case`.

Discover the full structure yourself by inspecting the source:

```bash
find claude_code_src/src -type d | sort
find claude_code_src/src -type f -name "*.ts" | sort
```

---

## What Already Exists

Current `optimus/` contains:
- `types/` — message, permissions, tools, hooks, ids, logs types
- `constants/` — common and tools constants
- `utils/` — env_utils, features
- `tool.py` — Tool Protocol, ToolUseContext, build_tool factory
- `tools.py` — tool registry

Before writing anything, check what's already there. Extend it. Stay consistent with the patterns already established.

---

## Definition of Done

- Every file in `src/` has a Python equivalent in `optimus/`
- `mypy --strict optimus/` passes with 0 errors
- Full test suite passes
- `optimus` CLI launches, `--help` works, REPL mode is functional
- All tools registered and callable
- All slash commands registered
- MCP, agent/swarm, history — all functional
- `PORTING_NOTES.md` is complete
- Zero unimplemented stubs remain

---

*OPTIMUS Mark I — Python port of Claude Code*
*Author: Ahmet Erol Bayrak*
