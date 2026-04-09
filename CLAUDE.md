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

## ⛔ The Line-Count Rule — MANDATORY

Every ported file must be cross-checked against the TypeScript original by line count.

**A Python file that is dramatically shorter than its TypeScript source is a red flag and almost certainly a stub or a partial port.** Before committing any file, verify:

```
TS source lines  →  Python lines
-------------------------------------
bashSecurity.ts    2592  →  bash_security.py    must be ≥ 400 non-comment lines
bashPermissions.ts 2621  →  bash_permissions.py must be ≥ 500 non-comment lines
pathValidation.ts  1990  →  path_validation.py  must be ≥ 350 non-comment lines
commands.ts        1339  →  commands.py         must be ≥ 250 non-comment lines
```

Python is more concise than TypeScript. But if a 2000-line TS file produces an 80-line Python file, that is not a port — it is a skeleton. The minimum acceptable ratio is roughly **1 Python line per 4–5 TS lines** for large files (types, JSDoc, braces inflate TS). If the ratio is worse than 1:8, treat it as incomplete and go back to the source.

---

## ⛔ The "No Thin Wrapper" Rule — MANDATORY

Do not write a thin wrapper that:
- Imports 2–3 things and re-exports them
- Has a class with `pass` or `...` as the body
- Has methods that return `None` without performing the actual logic
- Has functions that raise `NotImplementedError`
- Delegates everything to `try: from ... import X; X()` without the actual logic

Every function must contain the **real logic** from the TypeScript source. If a dependency module hasn't been ported yet, either port it first or write a clearly-marked stub with a `# TODO: port <filename>.ts` comment and file a note in `PORTING_NOTES.md`. Do not silently omit logic.

---

## ⛔ The "Read the Whole File" Rule — MANDATORY

Before implementing any module:

1. Read the **entire** TypeScript source file from line 1 to the last line
2. Count the exported functions — every one must have a Python equivalent
3. Note all constants, all enums, all type aliases — every one must be ported
4. Note the imports — every dependency that contains logic must either be already ported or explicitly stubs

Partial reads lead to partial ports. If a file is 3000 lines, read all 3000 lines before writing a single line of Python.

---

## ⛔ The Status+README Maintenance Rule — MANDATORY

After every session that adds or changes files:

1. **Update `STATUS.md`** — move completed items to "What's Done", update the file count, update "What's Next" to reflect only items that are actually not yet ported
2. **Update `README.md`** — keep the "What's built" table and roadmap current

The "What's Next" section must **never** list items that are already done. Listing `bash_tool.py` as pending when it already exists, or listing `bash_security.py` as needed when it was just written — that is a lie in the documentation and makes it impossible to track real progress.

---

## ⛔ The "No False Progress" Rule — MANDATORY

Do not claim a module is "done" if:
- It has unexplained `pass` statements in non-exception-handler positions
- It has functions that do nothing (no side effects, no return value, no logic)
- It delegates to modules that don't exist yet without documenting that
- It silently ignores entire sections of the TypeScript source

When a module has a genuine dependency that hasn't been ported yet, that dependency is a blocker. Document it. Don't silently omit the logic that depends on it.

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
| `feature('FLAG')` Bun DCE | `False` constant (feature flags are off in Python port) |
| `logEvent(...)` analytics | no-op / omit |

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

Read `STATUS.md` before every session. It is the authoritative record of what has and has not been ported. Do not re-port things that exist. Do not claim things are done when they are not.

The "What Already Exists" list in this file is intentionally kept short — go read `STATUS.md` for the real inventory.

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
- `STATUS.md` accurately reflects the above

---

*OPTIMUS Mark I — Python port of Claude Code*
*Author: Ahmet Erol Bayrak*
