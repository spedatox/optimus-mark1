# PORTING NOTES — OPTIMUS Mark I

Python port of Claude Code (TypeScript/Bun) by Ahmet Erol Bayrak.

---

## Missing Source Files

The `claude_code.zip` archive is missing several files that are referenced by imports:
- `src/types/message.ts` — reconstructed from usage across ~200 importing files
- `src/types/tools.ts` — reconstructed from progress type usage in individual tool files
- `src/types/connectorText.ts` — reconstructed from usage
- `src/types/messageQueueTypes.ts` — reconstructed from usage

These files were reconstructed by analyzing the import names, construction sites (`createAssistantMessage`, `createUserMessage`), and consumption patterns.

---

## TypeScript → Python Adaptations

### Bun-specific Features
- `import { feature } from 'bun:bundle'` — compile-time feature flags in Bun.
  **Python equivalent**: `os.environ.get('FEATURE_FOO', 'false').lower() == 'true'`
  We define a `features.py` module with `feature(name: str) -> bool` that reads env vars.

### Type System
- TypeScript branded types (`string & { __brand: 'Foo' }`) → Python `typing.NewType`
- TypeScript `interface Foo` → Python `TypedDict` or `@dataclass`
- TypeScript `type Foo = A | B` → Python `Union[A, B]` or `Foo = A | B` (3.12+)
- TypeScript `readonly` → Python `Final` or frozen dataclasses
- TypeScript `z.object(...)` Zod schemas → Pydantic `BaseModel`
- TypeScript generic types `Tool<Input, Output, P>` → Python `Generic[Input, Output, P]`

### React/Ink → Textual
- React components → Textual `Widget` subclasses
- React hooks (`useState`, `useEffect`) → Textual reactive attributes and `watch_*` methods
- JSX rendering → Textual's `compose()` and `render()` methods
- `React.ReactNode` → `textual.widget.Widget | str | None`
- The `SetToolJSXFn` callback → Python callable that updates a Textual widget slot

### Async Model
- Bun's async/await → Python `asyncio`
- `Promise.all([...])` → `asyncio.gather(...)`
- `EventEmitter` → `pyee.AsyncIOEventEmitter`
- Generator functions → Python `async def` with `asyncio.Queue`

### Module System
- `import { feature } from 'bun:bundle'` → env var check
- Circular dependency lazy `require(...)` → Python `importlib.import_module()` deferred imports
- `index.ts` barrel files → `__init__.py` with `__all__`

### Tool System
- `buildTool(def)` → Python `build_tool(def_)` function that applies defaults via `dict | defaults`
- `satisfies ToolDef<...>` TypeScript type assertion → Python `Protocol` conformance check
- Zod schema `z.object({...})` for input validation → Pydantic `BaseModel`
- `z.infer<Input>` → Pydantic model instance

### Permission System
- `ToolPermissionContext` uses TypeScript's `DeepImmutable<>` → Python frozen dataclass
- `PermissionMode` string literal union → Python `Literal[...]` type alias

### MCP Integration
- `@modelcontextprotocol/sdk` → `mcp` Python SDK
- `MCPServerConnection` → Python dataclass mirroring the TS type

---

## Architecture Decisions

### Progress Types
The original uses TypeScript discriminated unions for progress data
(`type: 'bash_progress' | 'agent_progress' | ...`). Python equivalent:
each progress variant is a Pydantic model with a `type: Literal[...]` field,
and `ToolProgressData` is their union.

### Message Types
`AssistantMessage` and `UserMessage` are TypeScript discriminated unions on `type`.
Python: use `@dataclass` with `type: Literal['assistant']` / `Literal['user']` fields.
The `Message` union is `Union[AssistantMessage, UserMessage, SystemMessage, ...]`.

### Feature Flags
The source uses `feature('FLAG_NAME')` from `bun:bundle` which is a compile-time
dead-code elimination mechanism. In Python we replace this with runtime env var checks
via `optimus/utils/features.py::feature(name) -> bool`.

### File Layout
- `native-ts/` → `optimus/native/` (hyphen → underscore)
- `outputStyles/` → `optimus/output_styles/`
- `upstreamproxy/` → `optimus/upstream_proxy/`
- All camelCase dirs → snake_case dirs

---

## Phase Log

- **Phase 0** (2026-04-05): Scaffold created — 297 packages, pyproject.toml, PORTING_NOTES.md
- **Phase 1** (2026-04-05): Core type system ported — types/message.py, types/permissions.py, types/ids.py, types/hooks.py, types/tools.py (logs.py)
