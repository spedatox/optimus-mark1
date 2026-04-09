"""
Shell command quoting helpers.

Python port of src/utils/bash/shellQuoting.ts

Provides:
  - quote_shell_command()      — quote a command for use inside eval, handling
                                 heredocs and multiline strings specially.
  - has_stdin_redirect()       — detect existing stdin redirects.
  - should_add_stdin_redirect() — decide whether < /dev/null can be appended.
  - rewrite_windows_null_redirect() — replace Windows '>nul' with '>/dev/null'.
"""
from __future__ import annotations

import re

from optimus.utils.bash.shell_quote import quote

# ---------------------------------------------------------------------------
# Heredoc / multiline detection
# ---------------------------------------------------------------------------

_HEREDOC_BITSHIFT_RE = re.compile(r"\d\s*<<\s*\d|\[\[\s*\d+\s*<<\s*\d+\s*\]\]|\$\(\(.*<<.*\)\)")
_HEREDOC_RE = re.compile(r"<<-?\s*(?:(['\"]?)(\w+)\1|\\(\w+))")


def _contains_heredoc(command: str) -> bool:
    """Return True if *command* contains a heredoc (<<) operator."""
    if _HEREDOC_BITSHIFT_RE.search(command):
        return False
    return bool(_HEREDOC_RE.search(command))


def _contains_multiline_string(command: str) -> bool:
    """Return True if *command* contains a quoted string spanning multiple lines."""
    single_quote_multiline = re.compile(r"'(?:[^'\\]|\\.)*\n(?:[^'\\]|\\.)*'")
    double_quote_multiline = re.compile(r'"(?:[^"\\]|\\.)*\n(?:[^"\\]|\\.)*"')
    return bool(single_quote_multiline.search(command) or double_quote_multiline.search(command))


def _single_quote_for_eval(s: str) -> str:
    """
    Single-quote a string for use as an eval argument.

    Embedded single quotes are escaped via '"'"' (close-sq, literal-sq-in-dq,
    reopen-sq).  This avoids shell-quote's aggressive ! → \\! conversion that
    corrupts jq/awk filters like select(.x != .y).

    Mirrors singleQuoteForEval() from bashPipeCommand.ts.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------------------
# quote_shell_command
# ---------------------------------------------------------------------------


def quote_shell_command(command: str, add_stdin_redirect: bool = True) -> str:
    """
    Quote a shell command for use inside eval, preserving heredocs.

    Mirrors quoteShellCommand() from shellQuoting.ts.

    For heredocs and multiline strings we switch to a manual single-quote
    escaping approach (avoiding shell-quote's \\! corruption).

    Args:
        command:            The shell command string to quote.
        add_stdin_redirect: Whether to append ``< /dev/null``.

    Returns:
        A quoted string suitable for ``eval <result>``.
    """
    if _contains_heredoc(command) or _contains_multiline_string(command):
        # Manual single-quote escaping: ' becomes '"'"'
        escaped = command.replace("'", "'\"'\"'")
        quoted = f"'{escaped}'"

        # Heredocs supply their own stdin — don't add the redirect
        if _contains_heredoc(command):
            return quoted

        # Multiline strings without heredoc
        if add_stdin_redirect:
            return f"{quoted} < /dev/null"
        return quoted

    # Regular commands: use shell-quote
    if add_stdin_redirect:
        return quote([command, "<", "/dev/null"])

    return quote([command])


# ---------------------------------------------------------------------------
# stdin-redirect helpers
# ---------------------------------------------------------------------------


def has_stdin_redirect(command: str) -> bool:
    """
    Return True if *command* already contains a stdin redirect (< file).

    Excludes heredoc (<<) and process substitution (<(…)).
    Mirrors hasStdinRedirect() from shellQuoting.ts.
    """
    return bool(re.search(r"(?:^|[\s;&|])<(?![<(])\s*\S+", command))


def should_add_stdin_redirect(command: str) -> bool:
    """
    Return True if < /dev/null can safely be appended to *command*.

    Mirrors shouldAddStdinRedirect() from shellQuoting.ts.
    """
    if _contains_heredoc(command):
        return False
    if has_stdin_redirect(command):
        return False
    return True


# ---------------------------------------------------------------------------
# Windows null redirect rewrite
# ---------------------------------------------------------------------------

_NUL_REDIRECT_RE = re.compile(
    r"(\d?&?>+\s*)[Nn][Uu][Ll](?=\s|$|[|&;)\n])"
)


def rewrite_windows_null_redirect(command: str) -> str:
    """
    Replace Windows CMD-style ``>nul`` / ``2>nul`` / ``>NUL`` redirects with
    the POSIX equivalent ``>/dev/null``.

    The model occasionally emits ``2>nul`` even when targeting a POSIX shell.
    In Git Bash on Windows this creates a literal file named ``nul`` — a
    reserved device name that is extremely hard to delete.

    Mirrors rewriteWindowsNullRedirect() from shellQuoting.ts.
    """
    return _NUL_REDIRECT_RE.sub(r"\1/dev/null", command)
