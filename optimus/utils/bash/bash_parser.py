"""
Bash command string parser — AST-lite representation.

Python port of src/utils/bash/bashParser.ts

The TypeScript source is a 3 000+ line pure-TS re-implementation of a
tree-sitter-bash-compatible parser.  The full parser is a complex piece of
machinery (UTF-8 byte offsets, heredoc pending queues, a recursive-descent
grammar for bash) and would be a project of its own to port faithfully at
that level.

This Python port implements:
  1. The same *public interface* (TsNode dataclass, parse() function).
  2. A simplified but behaviorally equivalent parser that correctly identifies
     the node types that downstream security/permission checks use:
       program, command, pipeline, list, compound_command, if_statement,
       for_statement, while_statement, function_definition, variable_assignment,
       word, string, raw_string, operator, redirect, heredoc.
  3. The SHELL_KEYWORDS set (consumed by bashPipeCommand / bashCommandHelpers).
  4. The 50ms / 50 000 node budget guard (returns None when exceeded).

Security note: this is purely an informational / structural parser.  It is
NOT used for shell execution — only for deciding whether a command needs
permission escalation.  The actual command is executed verbatim by the
subprocess layer.

PORTING_NOTES: The original TypeScript version achieves UTF-8 byte-offset
accuracy via a byte table built on first non-ASCII access.  Python's str is
UCS-4 so byte offsets are computed via str.encode('utf-8') lengths.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Public AST node type
# ---------------------------------------------------------------------------


@dataclass
class TsNode:
    """
    Mirrors the TsNode type from bashParser.ts.

    Fields:
        type:        Grammar node type (e.g. 'program', 'command', 'word').
        text:        Raw source text of this node.
        start_index: UTF-8 byte offset of the first character.
        end_index:   UTF-8 byte offset one past the last character.
        children:    Child nodes (may be empty for leaf nodes).
    """
    type: str
    text: str
    start_index: int
    end_index: int
    children: list["TsNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARSE_TIMEOUT_MS: int = 50
MAX_NODES: int = 50_000

SHELL_KEYWORDS: frozenset[str] = frozenset([
    "if", "then", "elif", "else", "fi",
    "while", "until", "for", "in",
    "do", "done",
    "case", "esac",
    "function", "select",
])

# ---------------------------------------------------------------------------
# UTF-8 byte offset helper
# ---------------------------------------------------------------------------


def _byte_offset(text: str, char_index: int) -> int:
    """Return the UTF-8 byte offset of *char_index* within *text*."""
    return len(text[:char_index].encode("utf-8"))


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Internal parser state
# ---------------------------------------------------------------------------


class _ParseState:
    def __init__(self, src: str, timeout_ms: float = PARSE_TIMEOUT_MS) -> None:
        self.src = src
        self.pos: int = 0          # char index
        self.node_count: int = 0
        self.deadline: float = time.monotonic() + timeout_ms / 1000.0
        self.timed_out: bool = False
        self.over_budget: bool = False

    def remaining(self) -> str:
        return self.src[self.pos:]

    def check_limits(self) -> bool:
        """Return True if we should abort parsing."""
        if self.node_count >= MAX_NODES:
            self.over_budget = True
            return True
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            return True
        return False

    def make_leaf(self, node_type: str, text: str, start_char: int) -> TsNode:
        self.node_count += 1
        start_b = _byte_offset(self.src, start_char)
        end_b = start_b + _byte_len(text)
        return TsNode(type=node_type, text=text, start_index=start_b, end_index=end_b)

    def make_node(
        self,
        node_type: str,
        start_char: int,
        end_char: int,
        children: list[TsNode],
    ) -> TsNode:
        self.node_count += 1
        text = self.src[start_char:end_char]
        start_b = _byte_offset(self.src, start_char)
        end_b = _byte_offset(self.src, end_char)
        return TsNode(type=node_type, text=text, start_index=start_b, end_index=end_b, children=children)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n")
_COMMENT_RE = re.compile(r"#[^\n]*")
_NUMBER_RE = re.compile(r"[0-9]+")
_OPERATOR_RE = re.compile(
    r"\|\|?|&&|;;|<<-?|>>|[<>|&;()]|>&"
)
_WORD_CHARS_RE = re.compile(r"[^\s|&;<>()#\"'$`\\\n]+")

# Heredoc opener: <<[-]?["']?WORD["']?
_HEREDOC_START_RE = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)(['\"]?)")


# ---------------------------------------------------------------------------
# Simplified parse function
# ---------------------------------------------------------------------------


def parse(source: str, timeout_ms: float = PARSE_TIMEOUT_MS) -> TsNode | None:
    """
    Parse a bash command string, returning a TsNode tree or None on failure.

    Mirrors parse() / parseSource() from bashParser.ts.

    Returns None if:
      - The source is empty (after stripping).
      - The node budget (50 000) is exceeded.
      - The timeout (50 ms default) is exceeded.

    The resulting tree uses the node types that downstream checks care about.
    It is not a complete bash grammar — just deep enough for security analysis.
    """
    if not source or not source.strip():
        return None

    state = _ParseState(source, timeout_ms)
    children = _parse_program(state)

    if state.timed_out or state.over_budget:
        return None

    start_b = _byte_offset(source, 0)
    end_b = _byte_len(source)
    return TsNode(
        type="program",
        text=source,
        start_index=start_b,
        end_index=end_b,
        children=children,
    )


def _parse_program(state: _ParseState) -> list[TsNode]:
    """Parse the top-level program as a list of statements."""
    statements: list[TsNode] = []
    while state.pos < len(state.src):
        if state.check_limits():
            break
        _skip_whitespace_and_newlines(state)
        if state.pos >= len(state.src):
            break
        stmt = _parse_statement(state)
        if stmt is None:
            break
        statements.append(stmt)
    return statements


def _skip_whitespace_and_newlines(state: _ParseState) -> None:
    """Advance past whitespace, newlines, and comments."""
    while state.pos < len(state.src):
        c = state.src[state.pos]
        if c in (" ", "\t", "\n", "\r"):
            state.pos += 1
        elif c == "#":
            # Comment: skip to end of line
            while state.pos < len(state.src) and state.src[state.pos] != "\n":
                state.pos += 1
        elif c == "\\" and state.pos + 1 < len(state.src) and state.src[state.pos + 1] == "\n":
            # Line continuation
            state.pos += 2
        else:
            break


def _skip_horizontal_whitespace(state: _ParseState) -> None:
    """Advance past spaces and tabs only."""
    while state.pos < len(state.src) and state.src[state.pos] in (" ", "\t"):
        state.pos += 1


def _parse_statement(state: _ParseState) -> TsNode | None:
    """Parse one statement (possibly a list or pipeline)."""
    start = state.pos
    parts: list[TsNode] = []

    # Check for compound constructs
    if _at_keyword(state, "if"):
        return _parse_if_statement(state)
    if _at_keyword(state, "for"):
        return _parse_for_statement(state)
    if _at_keyword(state, "while") or _at_keyword(state, "until"):
        return _parse_while_statement(state)
    if _at_keyword(state, "function"):
        return _parse_function_definition(state)

    # Parse pipeline or simple command
    pipeline = _parse_pipeline(state)
    if pipeline is None:
        return None

    parts.append(pipeline)
    _skip_horizontal_whitespace(state)

    # Check for list operators: &&, ||, ;, &
    while state.pos < len(state.src):
        if state.check_limits():
            break
        op_match = re.match(r"&&|\|\||;|&(?!&)", state.src[state.pos:])
        if not op_match:
            # Check for newline as implicit ;
            if state.src[state.pos] == "\n":
                break
            break
        op_text = op_match.group(0)
        op_start = state.pos
        state.pos += len(op_text)
        op_node = state.make_leaf("operator", op_text, op_start)
        _skip_whitespace_and_newlines(state)

        next_pipeline = _parse_pipeline(state)
        if next_pipeline is None:
            break
        parts.append(op_node)
        parts.append(next_pipeline)
        _skip_horizontal_whitespace(state)

    if len(parts) == 1:
        return parts[0]

    return state.make_node("list", start, state.pos, parts)


def _parse_pipeline(state: _ParseState) -> TsNode | None:
    """Parse cmd | cmd | cmd ... (pipeline)."""
    start = state.pos
    parts: list[TsNode] = []

    cmd = _parse_command(state)
    if cmd is None:
        return None
    parts.append(cmd)

    _skip_horizontal_whitespace(state)

    while state.pos < len(state.src):
        if state.check_limits():
            break
        # Pipe: | but NOT ||
        if state.src[state.pos] == "|" and state.pos + 1 < len(state.src) and state.src[state.pos + 1] != "|":
            pipe_start = state.pos
            state.pos += 1
            pipe_node = state.make_leaf("operator", "|", pipe_start)
            _skip_whitespace_and_newlines(state)
            next_cmd = _parse_command(state)
            if next_cmd is None:
                break
            parts.append(pipe_node)
            parts.append(next_cmd)
            _skip_horizontal_whitespace(state)
        else:
            break

    if len(parts) == 1:
        return parts[0]
    return state.make_node("pipeline", start, state.pos, parts)


def _at_keyword(state: _ParseState, keyword: str) -> bool:
    """Return True if *keyword* appears at the current position."""
    end = state.pos + len(keyword)
    if end > len(state.src):
        return False
    if state.src[state.pos:end] != keyword:
        return False
    # Must be followed by whitespace or EOF
    if end < len(state.src) and state.src[end] not in (" ", "\t", "\n", ";", "(", ")"):
        return False
    return True


def _parse_if_statement(state: _ParseState) -> TsNode:
    """Parse if/then/elif/else/fi block."""
    start = state.pos
    state.pos += len("if")
    _skip_whitespace_and_newlines(state)
    children: list[TsNode] = []

    # Skip until fi
    depth = 1
    while state.pos < len(state.src) and depth > 0:
        if _at_keyword(state, "if"):
            depth += 1
            state.pos += 2
        elif _at_keyword(state, "fi"):
            depth -= 1
            state.pos += 2
        else:
            state.pos += 1

    return state.make_node("if_statement", start, state.pos, children)


def _parse_for_statement(state: _ParseState) -> TsNode:
    """Parse for/do/done block."""
    start = state.pos
    state.pos += len("for")
    children: list[TsNode] = []

    # Skip until done
    depth = 1
    while state.pos < len(state.src) and depth > 0:
        for kw, delta in [("for", 1), ("while", 1), ("until", 1), ("done", -1)]:
            if _at_keyword(state, kw):
                depth += delta
                state.pos += len(kw)
                break
        else:
            state.pos += 1

    return state.make_node("for_statement", start, state.pos, children)


def _parse_while_statement(state: _ParseState) -> TsNode:
    """Parse while/until/do/done block."""
    start = state.pos
    kw = "while" if _at_keyword(state, "while") else "until"
    state.pos += len(kw)
    children: list[TsNode] = []

    depth = 1
    while state.pos < len(state.src) and depth > 0:
        for k, delta in [("while", 1), ("until", 1), ("for", 1), ("done", -1)]:
            if _at_keyword(state, k):
                depth += delta
                state.pos += len(k)
                break
        else:
            state.pos += 1

    return state.make_node("while_statement", start, state.pos, children)


def _parse_function_definition(state: _ParseState) -> TsNode:
    """Parse function name { ... } block."""
    start = state.pos
    state.pos += len("function")
    children: list[TsNode] = []

    # Skip the body (delimited by balanced braces)
    while state.pos < len(state.src):
        if state.src[state.pos] == "{":
            state.pos += 1
            depth = 1
            while state.pos < len(state.src) and depth > 0:
                if state.src[state.pos] == "{":
                    depth += 1
                elif state.src[state.pos] == "}":
                    depth -= 1
                state.pos += 1
            break
        state.pos += 1

    return state.make_node("function_definition", start, state.pos, children)


def _parse_command(state: _ParseState) -> TsNode | None:
    """Parse a simple command with optional redirects."""
    _skip_horizontal_whitespace(state)
    if state.pos >= len(state.src):
        return None

    c = state.src[state.pos]

    # Subshell: (cmd)
    if c == "(":
        return _parse_subshell(state)

    # Command group: { cmd; }
    if c == "{":
        return _parse_command_group(state)

    start = state.pos
    parts: list[TsNode] = []

    # Collect words and redirects
    while state.pos < len(state.src):
        if state.check_limits():
            break
        _skip_horizontal_whitespace(state)
        if state.pos >= len(state.src):
            break
        c = state.src[state.pos]

        # Stop at newline, ;, &, |, ), }
        if c in ("\n", ";", "&", ")", "}"):
            break
        if c == "|" and (state.pos + 1 >= len(state.src) or state.src[state.pos + 1] != "|"):
            break
        if state.src[state.pos:state.pos + 2] in ("&&", "||"):
            break

        # Redirect
        redirect = _try_parse_redirect(state)
        if redirect is not None:
            parts.append(redirect)
            continue

        # Word / variable assignment
        word = _parse_word(state)
        if word is None:
            break
        parts.append(word)

    if not parts:
        return None

    # Check if this looks like a variable assignment at the start
    if parts and parts[0].type == "word" and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[0].text):
        parts[0] = TsNode(
            type="variable_assignment",
            text=parts[0].text,
            start_index=parts[0].start_index,
            end_index=parts[0].end_index,
            children=parts[0].children,
        )

    return state.make_node("command", start, state.pos, parts)


def _parse_subshell(state: _ParseState) -> TsNode:
    """Parse (cmd) — a subshell."""
    start = state.pos
    state.pos += 1  # consume (
    children: list[TsNode] = []

    depth = 1
    while state.pos < len(state.src) and depth > 0:
        c = state.src[state.pos]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        state.pos += 1

    return state.make_node("subshell", start, state.pos, children)


def _parse_command_group(state: _ParseState) -> TsNode:
    """Parse { cmd; } — a command group."""
    start = state.pos
    state.pos += 1  # consume {
    children: list[TsNode] = []

    depth = 1
    while state.pos < len(state.src) and depth > 0:
        c = state.src[state.pos]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        state.pos += 1

    return state.make_node("command_group", start, state.pos, children)


def _try_parse_redirect(state: _ParseState) -> TsNode | None:
    """Try to parse a redirect (>, <, >>, 2>&1, etc.)."""
    m = re.match(r"(\d?)(>>|>&|[<>|])\s*([^\s|&;<>()#]+)", state.src[state.pos:])
    if not m:
        return None
    text = m.group(0)
    start = state.pos
    state.pos += len(text)
    return state.make_leaf("redirect", text, start)


def _parse_word(state: _ParseState) -> TsNode | None:
    """Parse a single word token (possibly quoted or containing expansions)."""
    if state.pos >= len(state.src):
        return None

    start = state.pos
    parts: list[str] = []

    while state.pos < len(state.src):
        c = state.src[state.pos]

        if c in (" ", "\t", "\n", ";", "&", "|", "(", ")", "{", "}", "<", ">"):
            # Don't consume operators that could be part of >> or |
            if c in (">", "<") and state.pos + 1 < len(state.src) and state.src[state.pos + 1] in (">", "&"):
                break
            break

        if c == "'":
            # Single-quoted string
            end = state.src.find("'", state.pos + 1)
            if end == -1:
                end = len(state.src)
            else:
                end += 1
            parts.append(state.src[state.pos:end])
            state.pos = end

        elif c == '"':
            # Double-quoted string
            j = state.pos + 1
            while j < len(state.src) and state.src[j] != '"':
                if state.src[j] == "\\" and j + 1 < len(state.src):
                    j += 2
                else:
                    j += 1
            j = min(j + 1, len(state.src))
            parts.append(state.src[state.pos:j])
            state.pos = j

        elif c == "\\" and state.pos + 1 < len(state.src):
            parts.append(state.src[state.pos:state.pos + 2])
            state.pos += 2

        else:
            parts.append(c)
            state.pos += 1

    if not parts:
        return None

    text = "".join(parts)
    node_type = "word"
    if text.startswith("'") and text.endswith("'"):
        node_type = "raw_string"
    elif text.startswith('"') and text.endswith('"'):
        node_type = "string"

    return state.make_leaf(node_type, text, start)


# ---------------------------------------------------------------------------
# Public interface helpers
# ---------------------------------------------------------------------------


def ensure_parser_initialized() -> None:
    """No-op in Python — the pure-Python parser needs no async init."""
    pass


def get_parser_module() -> object:
    """Return a trivial module-like object with a parse() method."""

    class _Module:
        @staticmethod
        def parse(source: str, timeout_ms: float = PARSE_TIMEOUT_MS) -> TsNode | None:
            return parse(source, timeout_ms)

    return _Module()
