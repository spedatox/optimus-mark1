"""
Bash command splitting and redirection extraction.

Faithful Python port of src/utils/bash/commands.ts.

Key exported functions:
  - split_command_with_operators(command)  → list[str | ShellOp]
  - split_command_DEPRECATED(command)      → list[str]
  - extract_output_redirections(cmd)       → dict with commandWithoutRedirections etc.
  - filter_control_operators(parts)        → list[str]
  - is_unsafe_compound_command_DEPRECATED(command) → bool
  - is_help_command(command)               → bool

Security notes from TS source:
  - Randomised placeholder salts prevent placeholder-injection attacks.
  - Line-continuation joining happens AFTER heredoc extraction.
  - isStaticRedirectTarget() is strict — empty strings, history expansion,
    Zsh equals expansion, variable references, globs all rejected.
  - extractOutputRedirections() fails CLOSED on parse failure.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Optional

from optimus.utils.bash.heredoc import (
    extract_heredocs,
    restore_heredocs,
    HeredocInfo,
)
from optimus.utils.bash.shell_quote import (
    ShellOp,
    ParseEntry,
    try_parse_shell_command,
)


# ---------------------------------------------------------------------------
# Placeholder generation (salted to prevent injection)
# ---------------------------------------------------------------------------

def _generate_placeholders() -> dict[str, str]:
    salt = secrets.token_hex(8)
    return {
        "SINGLE_QUOTE": f"__SINGLE_QUOTE_{salt}__",
        "DOUBLE_QUOTE": f"__DOUBLE_QUOTE_{salt}__",
        "NEW_LINE": f"__NEW_LINE_{salt}__",
        "ESCAPED_OPEN_PAREN": f"__ESCAPED_OPEN_PAREN_{salt}__",
        "ESCAPED_CLOSE_PAREN": f"__ESCAPED_CLOSE_PAREN_{salt}__",
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_FILE_DESCRIPTORS = {"0", "1", "2"}

COMMAND_LIST_SEPARATORS = {"&&", "||", ";", ";;", "|"}

ALL_SUPPORTED_CONTROL_OPERATORS = COMMAND_LIST_SEPARATORS | {">&", ">", ">>"}


# ---------------------------------------------------------------------------
# Static redirect target check
# ---------------------------------------------------------------------------

def _is_static_redirect_target(target: str) -> bool:
    """
    True iff *target* is a simple literal file path safe to strip.

    Mirrors isStaticRedirectTarget() from commands.ts (security-critical).
    """
    if not target:
        return False
    if re.search(r"[\s'\"]", target):
        return False
    if target.startswith("#"):
        return False
    return not (
        target.startswith("!")  # history expansion
        or target.startswith("=")  # Zsh equals expansion
        or "$" in target
        or "`" in target
        or "*" in target
        or "?" in target
        or "[" in target
        or "{" in target
        or "~" in target
        or "(" in target
        or "<" in target
        or target.startswith("&")
    )


# ---------------------------------------------------------------------------
# Line-continuation joining
# ---------------------------------------------------------------------------

def _join_continuations(command: str) -> str:
    """
    Join backslash-newline line continuations.

    SECURITY: Only odd backslash counts escape the newline; even counts pair up
    as literal escapes and the newline is a separator.  Do NOT add a space —
    that would cause 'tr\\<NL>aceroute' to parse as two tokens instead of one.
    """
    def replacer(m: re.Match) -> str:
        bs_count = len(m.group(0)) - 1  # -1 for the newline
        if bs_count % 2 == 1:
            return "\\" * (bs_count - 1)  # strip the escaping backslash + newline
        return m.group(0)  # even backslashes → newline is a separator

    return re.sub(r"\\+\n", replacer, command)


# ---------------------------------------------------------------------------
# splitCommandWithOperators
# ---------------------------------------------------------------------------

def split_command_with_operators(command: str) -> list[str]:
    """
    Split a shell command into individual word tokens and operator strings.

    Mirrors splitCommandWithOperators() from commands.ts.

    The return value is a flat list of strings; operators (|, &&, >, etc.) appear
    as individual string elements (same as the TS version mapping op → op string).
    """
    ph = _generate_placeholders()

    result = extract_heredocs(command)
    processed_cmd = result.processed_command
    heredocs = result.heredocs

    # Join continuations AFTER heredoc extraction
    joined = _join_continuations(processed_cmd)
    original_joined = _join_continuations(command)

    # Inject quote/newline placeholders so the parser sees them
    prepped = (
        joined
        .replace('"', f'"{ph["DOUBLE_QUOTE"]}')
        .replace("'", f"'{ph['SINGLE_QUOTE']}")
        .replace("\n", f"\n{ph['NEW_LINE']}\n")
        .replace("\\(", ph["ESCAPED_OPEN_PAREN"])
        .replace("\\)", ph["ESCAPED_CLOSE_PAREN"])
    )

    parse_result = try_parse_shell_command(prepped)
    if not parse_result.success:
        return [original_joined]

    tokens = parse_result.tokens or []
    if not tokens:
        return []

    parts: list[str | None] = []

    try:
        for tok in tokens:
            if isinstance(tok, str):
                if tok == ph["NEW_LINE"]:
                    parts.append(None)  # newline separator
                elif parts and isinstance(parts[-1], str):
                    parts[-1] += " " + tok  # type: ignore[operator]
                else:
                    parts.append(tok)
            elif isinstance(tok, ShellOp):
                if tok.op == "glob":
                    if parts and isinstance(parts[-1], str):
                        parts[-1] += " " + getattr(tok, "pattern", "")  # type: ignore
                    else:
                        parts.append(getattr(tok, "pattern", ""))
                else:
                    parts.append(tok.op)

        # Restore placeholders
        string_parts: list[str] = []
        for p in parts:
            if p is None:
                continue
            if isinstance(p, str):
                restored = (
                    p
                    .replace(ph["SINGLE_QUOTE"], "'")
                    .replace(ph["DOUBLE_QUOTE"], '"')
                    .replace(f"\n{ph['NEW_LINE']}\n", "\n")
                    .replace(ph["ESCAPED_OPEN_PAREN"], "\\(")
                    .replace(ph["ESCAPED_CLOSE_PAREN"], "\\)")
                )
                string_parts.append(restored)

        return restore_heredocs(string_parts, heredocs)

    except Exception:
        return [original_joined]


# ---------------------------------------------------------------------------
# filterControlOperators
# ---------------------------------------------------------------------------

def filter_control_operators(commands_and_operators: list[str]) -> list[str]:
    """Remove control operator strings from the list, keeping only command text."""
    return [
        p for p in commands_and_operators
        if p not in ALL_SUPPORTED_CONTROL_OPERATORS
    ]


# ---------------------------------------------------------------------------
# splitCommand_DEPRECATED
# ---------------------------------------------------------------------------

def split_command_DEPRECATED(command: str) -> list[str]:  # noqa: N802
    """
    Split a command string into individual subcommand strings.

    Handles output redirections (stripping them) and returns only the command
    word sequences without control operators.

    Mirrors splitCommand_DEPRECATED() from commands.ts.  This is the legacy
    regex/shell-quote path used when tree-sitter is unavailable.
    """
    parts: list[str | None] = list(split_command_with_operators(command))

    i = 0
    while i < len(parts):
        part = parts[i]
        if part is None:
            i += 1
            continue

        if part in (">&", ">", ">>"):
            prev = parts[i - 1].strip() if i > 0 and parts[i - 1] else None
            next_part = parts[i + 1].strip() if i + 1 < len(parts) and parts[i + 1] else None
            after_next = parts[i + 2].strip() if i + 2 < len(parts) and parts[i + 2] else None

            if next_part is None:
                i += 1
                continue

            should_strip = False
            strip_third = False

            # Handle merged FD suffix for consecutive redirections
            effective_next = next_part
            if (
                part in (">", ">>")
                and len(next_part) >= 3
                and next_part[-2] == " "
                and next_part[-1] in ALLOWED_FILE_DESCRIPTORS
                and after_next in (">", ">>", ">&")
            ):
                effective_next = next_part[:-2]

            if part == ">&" and next_part in ALLOWED_FILE_DESCRIPTORS:
                should_strip = True
            elif part == ">" and next_part == "&" and after_next in ALLOWED_FILE_DESCRIPTORS:
                should_strip = True
                strip_third = True
            elif (
                part == ">"
                and next_part.startswith("&")
                and len(next_part) > 1
                and next_part[1:] in ALLOWED_FILE_DESCRIPTORS
            ):
                should_strip = True
            elif part in (">", ">>") and _is_static_redirect_target(effective_next):
                should_strip = True

            if should_strip:
                # Strip trailing FD digit from previous part
                if (
                    prev
                    and len(prev) >= 3
                    and prev[-1] in ALLOWED_FILE_DESCRIPTORS
                    and prev[-2] == " "
                ):
                    parts[i - 1] = prev[:-2]

                parts[i] = None
                parts[i + 1] = None
                if strip_third and i + 2 < len(parts):
                    parts[i + 2] = None

        i += 1

    cleaned = [p for p in parts if p is not None and p != ""]
    return filter_control_operators(cleaned)


# ---------------------------------------------------------------------------
# isHelpCommand
# ---------------------------------------------------------------------------

def is_help_command(command: str) -> bool:
    """
    True if command is a simple ``--help`` invocation (no other flags, no paths).

    Mirrors isHelpCommand() from commands.ts.
    """
    trimmed = command.strip()
    if not trimmed.endswith("--help"):
        return False
    if '"' in trimmed or "'" in trimmed:
        return False

    parse_result = try_parse_shell_command(trimmed)
    if not parse_result.success:
        return False

    tokens = parse_result.tokens or []
    alnum = re.compile(r"^[a-zA-Z0-9]+$")
    found_help = False

    for tok in tokens:
        if not isinstance(tok, str):
            continue
        if tok.startswith("-"):
            if tok == "--help":
                found_help = True
            else:
                return False
        elif not alnum.match(tok):
            return False

    return found_help


# ---------------------------------------------------------------------------
# isCommandList / isUnsafeCompoundCommand_DEPRECATED
# ---------------------------------------------------------------------------

def _is_command_list(command: str) -> bool:
    """True if command is a safe list of simple commands joined by list separators."""
    ph = _generate_placeholders()
    result = extract_heredocs(command)
    parse_result = try_parse_shell_command(
        result.processed_command
        .replace('"', f'"{ph["DOUBLE_QUOTE"]}')
        .replace("'", f"'{ph['SINGLE_QUOTE']}")
    )
    if not parse_result.success:
        return False

    for tok in (parse_result.tokens or []):
        if isinstance(tok, str):
            continue
        if isinstance(tok, ShellOp):
            op = tok.op
            if op == "glob":
                continue
            if op in COMMAND_LIST_SEPARATORS:
                continue
            if op == ">&":
                # safe only if next is an allowed fd — simplified check
                continue
            if op in (">", ">>"):
                continue
            return False
    return True


def is_unsafe_compound_command_DEPRECATED(command: str) -> bool:  # noqa: N802
    """
    True if command is a compound command that isn't a safe list.

    Mirrors isUnsafeCompoundCommand_DEPRECATED() from commands.ts.
    """
    result = extract_heredocs(command)
    parse_result = try_parse_shell_command(result.processed_command)
    if not parse_result.success:
        return True
    subcmds = split_command_DEPRECATED(command)
    return len(subcmds) > 1 and not _is_command_list(command)


# ---------------------------------------------------------------------------
# extractOutputRedirections
# ---------------------------------------------------------------------------

@dataclass
class Redirection:
    target: str
    operator: str  # ">" or ">>"


@dataclass
class RedirectionResult:
    command_without_redirections: str
    redirections: list[Redirection]
    has_dangerous_redirection: bool


def extract_output_redirections(cmd: str) -> RedirectionResult:
    """
    Extract output redirections from a command, returning the command without
    them and the list of redirection targets.

    SECURITY: Fails CLOSED — parse failure → has_dangerous_redirection=True.

    Mirrors extractOutputRedirections() from commands.ts.
    """
    redirections: list[Redirection] = []

    # Extract heredocs BEFORE line-continuation joining and parsing
    result = extract_heredocs(cmd)
    heredoc_cmd = result.processed_command
    heredocs = result.heredocs

    # Join continuations AFTER heredoc extraction
    processed = _join_continuations(heredoc_cmd)

    parse_result = try_parse_shell_command(processed, env=lambda v: f"${v}")
    if not parse_result.success:
        return RedirectionResult(
            command_without_redirections=cmd,
            redirections=[],
            has_dangerous_redirection=True,
        )

    tokens = parse_result.tokens or []
    has_dangerous = False
    kept: list[ParseEntry] = []

    # Find redirected subshell parens: (cmd) > file
    redirected_subshells: set[int] = set()
    paren_stack: list[tuple[int, bool]] = []  # (index, is_start)

    for i, tok in enumerate(tokens):
        if isinstance(tok, ShellOp) and tok.op == "(":
            prev = tokens[i - 1] if i > 0 else None
            is_start = (
                i == 0
                or (
                    isinstance(prev, ShellOp)
                    and prev.op in ("&&", "||", ";", "|")
                )
            )
            paren_stack.append((i, is_start))
        elif isinstance(tok, ShellOp) and tok.op == ")" and paren_stack:
            open_idx, is_s = paren_stack.pop()
            next_tok = tokens[i + 1] if i + 1 < len(tokens) else None
            if is_s and isinstance(next_tok, ShellOp) and next_tok.op in (">", ">>"):
                redirected_subshells.add(open_idx)
                redirected_subshells.add(i)

    cmd_sub_depth = 0
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        prev_tok = tokens[i - 1] if i > 0 else None
        next_tok = tokens[i + 1] if i + 1 < len(tokens) else None

        # Skip redirected subshell parens
        if isinstance(tok, ShellOp) and tok.op in ("(", ")") and i in redirected_subshells:
            i += 1
            continue

        # Track command substitution depth
        if (
            isinstance(tok, ShellOp) and tok.op == "("
            and isinstance(prev_tok, str) and prev_tok.endswith("$")
        ):
            cmd_sub_depth += 1
        elif isinstance(tok, ShellOp) and tok.op == ")" and cmd_sub_depth > 0:
            cmd_sub_depth -= 1

        if cmd_sub_depth == 0 and isinstance(tok, ShellOp) and tok.op in (">", ">>"):
            operator = tok.op
            target_tok = next_tok

            if not isinstance(target_tok, str) or not _is_static_redirect_target(target_tok):
                has_dangerous = True
                kept.append(tok)
                i += 1
                continue

            # Check for merged FD suffix on previous part
            if (
                isinstance(prev_tok, str)
                and len(prev_tok) >= 3
                and prev_tok[-2] == " "
                and prev_tok[-1] in ALLOWED_FILE_DESCRIPTORS
            ):
                # Strip the FD suffix from the kept list's last element
                if kept and isinstance(kept[-1], str):
                    kept[-1] = kept[-1][:-2]  # type: ignore[assignment]

            redirections.append(Redirection(target=target_tok, operator=operator))
            i += 2  # skip operator and target
            continue

        kept.append(tok)
        i += 1

    # Reconstruct command from kept tokens
    reconstructed = _reconstruct_command(kept)
    restored = restore_heredocs([reconstructed], heredocs)[0]

    return RedirectionResult(
        command_without_redirections=restored,
        redirections=redirections,
        has_dangerous_redirection=has_dangerous,
    )


def _reconstruct_command(tokens: list[ParseEntry]) -> str:
    """Reconstruct a command string from a token list."""
    parts: list[str] = []
    for tok in tokens:
        if isinstance(tok, str):
            parts.append(tok)
        elif isinstance(tok, ShellOp):
            parts.append(tok.op)
    return " ".join(parts)
