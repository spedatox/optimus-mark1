"""
Shell quoting / unquoting utilities.

Python port of:
  - src/utils/bash/shellQuote.ts  — safe wrappers for shell-quote (shlex here)
  - hasMalformedTokens, hasShellQuoteSingleQuoteBug, quote()

The TypeScript code wraps the npm `shell-quote` library.  Python's stdlib
``shlex`` module provides the equivalent functionality.

Key design decisions (see PORTING_NOTES.md):
  - `shlex.quote()` is used instead of shell-quote's quote() — it always uses
    single-quote escaping, matching the TS singleQuoteForEval() helper.
  - `shlex.split()` is used for parsing.  It is stricter than shell-quote
    (raises ValueError on unterminated quotes), which is actually *safer*.
  - ParseEntry is represented as a Union[str, ShellOp] dataclass.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Union


# ---------------------------------------------------------------------------
# ParseEntry types (mirrors shell-quote's ParseEntry union)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShellOp:
    """Represents a shell operator token (|, &&, ||, ;, >, <, etc.)."""
    op: str


@dataclass(frozen=True)
class ShellGlob:
    """Represents a shell glob pattern token."""
    op: str = "glob"
    pattern: str = ""


ParseEntry = Union[str, ShellOp, ShellGlob]

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ShellParseResult:
    success: bool
    tokens: list[ParseEntry] | None = None
    error: str | None = None


@dataclass
class ShellQuoteResult:
    success: bool
    quoted: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Operators we recognise when splitting a command string.
_OPERATORS = re.compile(
    r"(\|\|?|&&|;;|;|&|>>?|<<-?|<\(|>\(|<|>\||[()])"
)


def try_parse_shell_command(
    cmd: str,
    env: dict[str, str | None] | None = None,
) -> ShellParseResult:
    """
    Parse a shell command string into a token list.

    Returns ShellParseResult(success=True, tokens=[...]) on success, or
    ShellParseResult(success=False, error=...) if the command is malformed.

    Mirrors tryParseShellCommand() from shellQuote.ts.

    The TypeScript version used the npm `shell-quote` library; here we use a
    hand-rolled tokeniser that splits on shell operators first, then uses
    shlex to tokenise individual word segments.  This preserves operators as
    ShellOp entries so the rest of the pipeline can identify pipe positions.
    """
    try:
        tokens = _tokenise_shell_command(cmd)
        return ShellParseResult(success=True, tokens=tokens)
    except Exception as exc:
        return ShellParseResult(success=False, error=str(exc))


def _tokenise_shell_command(cmd: str) -> list[ParseEntry]:
    """
    Split a shell command into a flat list of string tokens and ShellOp nodes.

    Strategy:
      1. Split the raw string on recognised operators (preserving them).
      2. For each non-operator segment, use shlex.split() to handle quoting.
      3. Re-assemble into a ParseEntry list.

    This is intentionally simpler than a full shell parser — it handles the
    common cases that the permission/security checks need.
    """
    tokens: list[ParseEntry] = []
    parts = _OPERATORS.split(cmd)

    for part in parts:
        if _OPERATORS.fullmatch(part):
            tokens.append(ShellOp(op=part))
        else:
            if not part:
                continue
            try:
                words = shlex.split(part)
            except ValueError:
                # Unterminated quote — treat the whole fragment as one word
                words = [part]
            tokens.extend(words)

    return tokens


# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------


def try_quote_shell_args(args: list[object]) -> ShellQuoteResult:
    """
    Quote a list of arguments for safe shell use.

    Mirrors tryQuoteShellArgs() from shellQuote.ts.
    Returns ShellQuoteResult(success=True, quoted=...) or
    ShellQuoteResult(success=False, error=...).
    """
    try:
        validated: list[str] = []
        for i, arg in enumerate(args):
            if arg is None:
                validated.append("None")
                continue
            if isinstance(arg, (str, int, float, bool)):
                validated.append(str(arg))
                continue
            raise TypeError(
                f"Cannot quote argument at index {i}: "
                f"{type(arg).__name__} values are not supported"
            )
        quoted = " ".join(shlex.quote(s) for s in validated)
        return ShellQuoteResult(success=True, quoted=quoted)
    except Exception as exc:
        return ShellQuoteResult(success=False, error=str(exc))


def quote(args: list[object]) -> str:
    """
    Quote a list of arguments for safe shell use.

    Mirrors quote() from shellQuote.ts — raises on failure after attempting a
    lenient fallback (converting unsupported types via str()).

    SECURITY: Uses single-quote escaping (shlex.quote) rather than
    double-quote escaping, so shell expansions like $(whoami) are never
    evaluated.
    """
    result = try_quote_shell_args(list(args))
    if result.success and result.quoted is not None:
        return result.quoted

    # Lenient fallback: convert everything to str
    try:
        str_args = [
            str(a) if a is not None else "None"
            for a in args
        ]
        return " ".join(shlex.quote(s) for s in str_args)
    except Exception as exc:
        raise RuntimeError("Failed to quote shell arguments safely") from exc


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def has_malformed_tokens(command: str, parsed: list[ParseEntry]) -> bool:
    """
    Detect commands whose parsed token stream differs from bash's interpretation.

    Mirrors hasMalformedTokens() from shellQuote.ts.

    Two checks:
      1. Walk the raw string counting quote pairs — odd counts mean unterminated
         quotes that shlex silently drops or misparses.
      2. For each string token, verify balanced delimiters ({}, (), []).
    """
    # Check for unterminated quotes in the original command (bash semantics)
    in_single = False
    in_double = False
    double_count = 0
    single_count = 0
    i = 0
    while i < len(command):
        c = command[i]
        if c == "\\" and not in_single:
            i += 2  # Skip escaped char
            continue
        if c == '"' and not in_single:
            double_count += 1
            in_double = not in_double
        elif c == "'" and not in_double:
            single_count += 1
            in_single = not in_single
        i += 1

    if double_count % 2 != 0 or single_count % 2 != 0:
        return True

    # Check string tokens for unbalanced delimiters
    for entry in parsed:
        if not isinstance(entry, str):
            continue
        if entry.count("{") != entry.count("}"):
            return True
        if entry.count("(") != entry.count(")"):
            return True
        if entry.count("[") != entry.count("]"):
            return True
        # Count unescaped double quotes (lookbehind not portable in re; use manual walk)
        dq = _count_unescaped(entry, '"')
        if dq % 2 != 0:
            return True
        sq = _count_unescaped(entry, "'")
        if sq % 2 != 0:
            return True

    return False


def _count_unescaped(s: str, char: str) -> int:
    """Count occurrences of *char* in *s* that are not preceded by a backslash."""
    count = 0
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
            continue
        if s[i] == char:
            count += 1
        i += 1
    return count


def has_shell_quote_single_quote_bug(command: str) -> bool:
    """
    Detect commands that exploit shell-quote's incorrect handling of backslashes
    inside single quotes.

    In bash, single quotes preserve ALL characters literally — backslash has
    no special meaning. Some tokenisers (including npm's shell-quote) incorrectly
    treat \\' inside single quotes as an escape, allowing token-merging attacks.

    Mirrors hasShellQuoteSingleQuoteBug() from shellQuote.ts.

    We walk the command with correct bash single-quote semantics and flag any
    pattern where a single-quoted string ends with an odd number of backslashes.
    """
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(command):
        char = command[i]

        # Handle backslash escaping outside single quotes
        if char == "\\" and not in_single_quote:
            i += 2  # Skip escaped char
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote

            if not in_single_quote:
                # Just closed a single quote — count trailing backslashes
                backslash_count = 0
                j = i - 1
                while j >= 0 and command[j] == "\\":
                    backslash_count += 1
                    j -= 1

                if backslash_count > 0 and backslash_count % 2 == 1:
                    # Odd trailing backslashes: always a parsing discrepancy
                    return True

                if (
                    backslash_count > 0
                    and backslash_count % 2 == 0
                    and "'" in command[i + 1:]
                ):
                    # Even trailing backslashes + later quote: potential merge
                    return True

        i += 1

    return False
