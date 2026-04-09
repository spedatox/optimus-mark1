"""
Bash pipe-command rearrangement utilities.

Python port of src/utils/bash/bashPipeCommand.ts

The core purpose: when a piped command is wrapped in ``eval '...' < /dev/null``
the stdin redirect lands on eval itself, not on the first command in the
pipeline.  This module detects the pipe boundary and inserts ``< /dev/null``
AFTER the first command rather than before eval.

Key public export:
  rearrange_pipe_command(command) -> str
    Returns a properly-quoted eval argument for the given command.

All helper functions are ported faithfully from the TypeScript source.
"""
from __future__ import annotations

import re
import shlex

from optimus.utils.bash.shell_quote import (
    ParseEntry,
    ShellGlob,
    ShellOp,
    has_malformed_tokens,
    has_shell_quote_single_quote_bug,
    quote,
    try_parse_shell_command,
)

# ---------------------------------------------------------------------------
# Control-structure detection
# ---------------------------------------------------------------------------

_CONTROL_STRUCTURE_RE = re.compile(r"\b(for|while|until|if|case|select)\s")


def _contains_control_structure(command: str) -> bool:
    """Return True if *command* contains a bash control structure keyword."""
    return bool(_CONTROL_STRUCTURE_RE.search(command))


# ---------------------------------------------------------------------------
# Continuation-line joining
# ---------------------------------------------------------------------------


def _join_continuation_lines(command: str) -> str:
    """
    Join backslash-newline continuation sequences.

    Odd number of trailing backslashes before a newline = line continuation.
    Even number = all pair up, the newline is a real separator.

    Mirrors joinContinuationLines() from bashPipeCommand.ts.
    """

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        backslash_count = len(m.group(0)) - 1  # -1 for the newline
        if backslash_count % 2 == 1:
            # Odd: last backslash is the continuation escape — remove it + newline
            return "\\" * (backslash_count - 1)
        # Even: all pair up; keep the newline
        return m.group(0)

    return re.sub(r"\\+\n", _replace, command)


# ---------------------------------------------------------------------------
# Single-quote-for-eval helpers
# ---------------------------------------------------------------------------


def _single_quote_for_eval(s: str) -> str:
    """
    Single-quote a string for use as an eval argument.

    Embedded single quotes become '"'"' (close-sq, dq-sq, open-sq).
    This avoids the ! → \\! corruption that double-quoting causes for jq/awk.

    Mirrors singleQuoteForEval() from bashPipeCommand.ts.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _quote_with_eval_stdin_redirect(command: str) -> str:
    """
    Quote *command* and append ``< /dev/null`` as a shell redirect on eval.

    Using ``singleQuoteForEval(cmd) + ' < /dev/null'`` produces:
        eval 'cmd' < /dev/null
    so eval's stdin is /dev/null and any pipes inside cmd work correctly.

    Mirrors quoteWithEvalStdinRedirect() from bashPipeCommand.ts.
    """
    return _single_quote_for_eval(command) + " < /dev/null"


# ---------------------------------------------------------------------------
# Pipe-index finder
# ---------------------------------------------------------------------------


def _find_first_pipe_operator(parsed: list[ParseEntry]) -> int:
    """
    Return the index of the first pipe (|) operator in *parsed*.
    Returns -1 if no pipe is found.

    Mirrors findFirstPipeOperator() from bashPipeCommand.ts.
    """
    for i, entry in enumerate(parsed):
        if isinstance(entry, ShellOp) and entry.op == "|":
            return i
    return -1


# ---------------------------------------------------------------------------
# Command-parts builder
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_COMMAND_SEPARATOR_OPS = {"&&", "||", ";"}


def _is_environment_variable_assignment(s: str) -> bool:
    return bool(_ENV_VAR_RE.match(s))


def _build_command_parts(
    parsed: list[ParseEntry],
    start: int,
    end: int,
) -> list[str]:
    """
    Reconstruct shell tokens from a slice of *parsed*, handling env-var
    assignments and FD redirections as special cases.

    Mirrors buildCommandParts() from bashPipeCommand.ts.
    """
    parts: list[str] = []
    seen_non_env_var = False
    i = start

    while i < end:
        entry = parsed[i]

        # Check for file descriptor redirections (2>&1, 2>/dev/null, etc.)
        if (
            isinstance(entry, str)
            and re.match(r"^[012]$", entry)
            and i + 2 < end
            and isinstance(parsed[i + 1], ShellOp)
        ):
            op = parsed[i + 1]
            assert isinstance(op, ShellOp)
            target = parsed[i + 2]

            # 2>&1 style
            if (
                op.op == ">&"
                and isinstance(target, str)
                and re.match(r"^[012]$", target)
            ):
                parts.append(f"{entry}>&{target}")
                i += 3
                continue

            # 2>/dev/null style
            if op.op == ">" and target == "/dev/null":
                parts.append(f"{entry}>/dev/null")
                i += 3
                continue

            # 2> &1 style (space between > and &1)
            if (
                op.op == ">"
                and isinstance(target, str)
                and target.startswith("&")
            ):
                fd = target[1:]
                if re.match(r"^[012]$", fd):
                    parts.append(f"{entry}>&{fd}")
                    i += 3
                    continue

        # Handle regular string tokens
        if isinstance(entry, str):
            is_env_var = (not seen_non_env_var) and _is_environment_variable_assignment(entry)
            if is_env_var:
                eq_idx = entry.index("=")
                name = entry[:eq_idx]
                value = entry[eq_idx + 1:]
                quoted_value = quote([value])
                parts.append(f"{name}={quoted_value}")
            else:
                seen_non_env_var = True
                parts.append(quote([entry]))

        elif isinstance(entry, ShellGlob):
            # Don't quote glob patterns — they need shell expansion
            parts.append(entry.pattern)

        elif isinstance(entry, ShellOp):
            parts.append(entry.op)
            if entry.op in _COMMAND_SEPARATOR_OPS:
                seen_non_env_var = False

        i += 1

    return parts


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


def rearrange_pipe_command(command: str) -> str:
    """
    Rearrange a piped command to place ``< /dev/null`` after the first command.

    Without this, ``eval 'cmd1 | cmd2' < /dev/null`` redirects eval's stdin
    rather than cmd1's.  With it, the first segment gets ``< /dev/null`` and
    the rest of the pipeline receives cmd1's stdout normally.

    Returns a quoted string suitable for use as an eval argument.

    Mirrors rearrangePipeCommand() from bashPipeCommand.ts.

    Bails to the simple eval+stdin-redirect form for any of:
      - Backtick command substitution (`cmd`)
      - $() command substitution
      - Shell variable references ($VAR, ${VAR})
      - Control structures (for/while/until/if/case/select)
      - Continuation lines that introduce real newlines
      - shell-quote single-quote-bug patterns
      - Parse failures or malformed tokens
      - Commands with no pipe at index > 0
    """
    # Bail out for patterns we cannot safely parse
    if "`" in command:
        return _quote_with_eval_stdin_redirect(command)
    if "$(" in command:
        return _quote_with_eval_stdin_redirect(command)
    if re.search(r"\$[A-Za-z_{]", command):
        return _quote_with_eval_stdin_redirect(command)
    if _contains_control_structure(command):
        return _quote_with_eval_stdin_redirect(command)

    joined = _join_continuation_lines(command)

    # Real newlines remaining after joining = bail
    if "\n" in joined:
        return _quote_with_eval_stdin_redirect(command)

    if has_shell_quote_single_quote_bug(joined):
        return _quote_with_eval_stdin_redirect(command)

    parse_result = try_parse_shell_command(joined)

    if not parse_result.success or parse_result.tokens is None:
        return _quote_with_eval_stdin_redirect(command)

    parsed = parse_result.tokens

    if has_malformed_tokens(joined, parsed):
        return _quote_with_eval_stdin_redirect(command)

    first_pipe_index = _find_first_pipe_operator(parsed)

    if first_pipe_index <= 0:
        return _quote_with_eval_stdin_redirect(command)

    # Rebuild: first_command < /dev/null | rest_of_pipeline
    parts = (
        _build_command_parts(parsed, 0, first_pipe_index)
        + ["< /dev/null"]
        + _build_command_parts(parsed, first_pipe_index, len(parsed))
    )

    return _single_quote_for_eval(" ".join(parts))
