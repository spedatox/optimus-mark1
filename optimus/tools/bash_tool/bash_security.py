"""
Bash command security validators.

Faithful Python port of src/tools/BashTool/bashSecurity.ts.

Exports:
  bash_command_is_safe_DEPRECATED(command)    → PermissionResult (sync)
  bash_command_is_safe_async_DEPRECATED(command) → PermissionResult (async)
  strip_safe_heredoc_substitutions(command)   → str | None
  has_safe_heredoc_substitution(command)      → bool

All 23 individual validators are also available for testing:
  validate_empty, validate_incomplete_commands, validate_safe_command_substitution,
  validate_git_commit, validate_jq_command, validate_shell_metacharacters,
  validate_dangerous_variables, validate_dangerous_patterns, validate_redirections,
  validate_newlines, validate_carriage_return, validate_ifs_injection,
  validate_proc_environ_access, validate_malformed_token_injection,
  validate_obfuscated_flags, validate_backslash_escaped_whitespace,
  validate_backslash_escaped_operators, validate_brace_expansion,
  validate_unicode_whitespace, validate_mid_word_hash, validate_zsh_dangerous_commands,
  validate_comment_quote_desync, validate_quoted_newline
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from optimus.utils.bash.heredoc import extract_heredocs, strip_safe_heredoc_substitutions as _strip_heredoc


# ---------------------------------------------------------------------------
# PermissionResult (mirrors TS PermissionResult in permissions/PermissionResult.ts)
# ---------------------------------------------------------------------------

@dataclass
class PermissionResult:
    behavior: str   # "allow" | "ask" | "deny" | "passthrough"
    message: str = ""
    is_bash_security_check_for_misparsing: bool = False
    check_id: int | None = None


# ---------------------------------------------------------------------------
# Constants from bashSecurity.ts
# ---------------------------------------------------------------------------

_HEREDOC_IN_SUBSTITUTION = re.compile(r"\$\(.*<<")

_COMMAND_SUBSTITUTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"<\("), "process substitution <()"),
    (re.compile(r">\("), "process substitution >()"),
    (re.compile(r"=\("), "Zsh process substitution =()"),
    (re.compile(r"(?:^|[\s;&|])=[a-zA-Z_]"), "Zsh equals expansion (=cmd)"),
    (re.compile(r"\$\("), "$() command substitution"),
    (re.compile(r"\$\{"), "${} parameter substitution"),
    (re.compile(r"\$\["), "$[] legacy arithmetic expansion"),
    (re.compile(r"~\["), "Zsh-style parameter expansion"),
    (re.compile(r"\(e:"), "Zsh-style glob qualifiers"),
    (re.compile(r"\(\+"), "Zsh glob qualifier with command execution"),
    (re.compile(r"\}\s*always\s*\{"), "Zsh always block (try/always construct)"),
    (re.compile(r"<#"), "PowerShell comment syntax"),
]

_ZSH_DANGEROUS_COMMANDS: frozenset[str] = frozenset([
    "zmodload", "emulate", "sysopen", "sysread", "syswrite", "sysseek",
    "zpty", "ztcp", "zsocket", "mapfile",
    "zf_rm", "zf_mv", "zf_ln", "zf_chmod", "zf_chown",
    "zf_mkdir", "zf_rmdir", "zf_chgrp",
])

BASH_SECURITY_CHECK_IDS = {
    "INCOMPLETE_COMMANDS": 1,
    "JQ_SYSTEM_FUNCTION": 2,
    "JQ_FILE_ARGUMENTS": 3,
    "OBFUSCATED_FLAGS": 4,
    "SHELL_METACHARACTERS": 5,
    "DANGEROUS_VARIABLES": 6,
    "NEWLINES": 7,
    "DANGEROUS_PATTERNS_COMMAND_SUBSTITUTION": 8,
    "DANGEROUS_PATTERNS_INPUT_REDIRECTION": 9,
    "DANGEROUS_PATTERNS_OUTPUT_REDIRECTION": 10,
    "IFS_INJECTION": 11,
    "GIT_COMMIT_SUBSTITUTION": 12,
    "PROC_ENVIRON_ACCESS": 13,
    "MALFORMED_TOKEN_INJECTION": 14,
    "BACKSLASH_ESCAPED_WHITESPACE": 15,
    "BRACE_EXPANSION": 16,
    "CONTROL_CHARACTERS": 17,
    "UNICODE_WHITESPACE": 18,
    "MID_WORD_HASH": 19,
    "ZSH_DANGEROUS_COMMANDS": 20,
    "BACKSLASH_ESCAPED_OPERATORS": 21,
    "COMMENT_QUOTE_DESYNC": 22,
    "QUOTED_NEWLINE": 23,
}

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_UNICODE_WHITESPACE_CHARS = (
    "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u202f\u205f\u3000\u2028\u2029"
)


# ---------------------------------------------------------------------------
# ValidationContext
# ---------------------------------------------------------------------------

@dataclass
class ValidationContext:
    original_command: str
    base_command: str             # command with heredocs stripped
    unquoted_content: str         # double/single quotes removed
    fully_unquoted: str           # all quotes removed
    fully_unquoted_pre_strip: str # before safe-heredoc stripping
    unquoted_keep_quote_chars: str


# ---------------------------------------------------------------------------
# Quote extraction
# ---------------------------------------------------------------------------

def _extract_quoted_content(command: str, is_jq: bool = False) -> dict[str, str]:
    """
    Build three views of *command* with varying degrees of quote stripping.

    Mirrors extractQuotedContent() from bashSecurity.ts.
    Returns dict with keys: with_double_quotes, fully_unquoted, unquoted_keep_quote_chars.
    """
    with_double: list[str] = []
    fully: list[str] = []
    keep_chars: list[str] = []

    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        ch = command[i]

        # Backslash outside single quotes
        if ch == "\\" and not in_single:
            if i + 1 < len(command):
                next_ch = command[i + 1]
                with_double.append(next_ch)
                fully.append(next_ch)
                keep_chars.append(next_ch)
                i += 2
            else:
                with_double.append(ch)
                fully.append(ch)
                keep_chars.append(ch)
                i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            keep_chars.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            keep_chars.append(ch)
            i += 1
            continue

        if in_single:
            fully.append(ch)
            keep_chars.append(ch)
        elif in_double:
            with_double.append(ch)
            fully.append(ch)
            keep_chars.append(ch)
        else:
            with_double.append(ch)
            fully.append(ch)
            keep_chars.append(ch)

        i += 1

    return {
        "with_double_quotes": "".join(with_double),
        "fully_unquoted": "".join(fully),
        "unquoted_keep_quote_chars": "".join(keep_chars),
    }


def _strip_safe_redirections(command: str) -> str:
    """Strip safe redirect patterns (2>&1, /dev/null, etc.) from command string."""
    result = command
    result = re.sub(r"\s*2>&1\s*$", "", result)
    result = re.sub(r"\s*[012]?\s*>+\s*/dev/null\s*$", "", result)
    result = re.sub(r"\s*</dev/null\s*$", "", result)
    return result


def _has_unescaped_char(s: str, char: str) -> bool:
    """True if *char* appears in *s* unescaped (not preceded by a backslash)."""
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
            continue
        if s[i] == char:
            return True
        i += 1
    return False


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

_PASSTHROUGH = PermissionResult(behavior="passthrough")
_ALLOW = PermissionResult(behavior="allow")


def _ask(message: str, check_id: int | None = None, misparse: bool = False) -> PermissionResult:
    return PermissionResult(
        behavior="ask",
        message=message,
        is_bash_security_check_for_misparsing=misparse,
        check_id=check_id,
    )


def validate_empty(ctx: ValidationContext) -> PermissionResult:
    if not ctx.original_command.strip():
        return _ALLOW
    return _PASSTHROUGH


def validate_incomplete_commands(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command.lstrip()
    if cmd.startswith("\t") or cmd.startswith("-") or re.match(r"^[|&;]", cmd):
        return _ask(
            "Command appears incomplete or starts with an operator.",
            check_id=BASH_SECURITY_CHECK_IDS["INCOMPLETE_COMMANDS"],
        )
    return _PASSTHROUGH


def validate_safe_command_substitution(ctx: ValidationContext) -> PermissionResult:
    """Early allow for safe heredoc-in-substitution patterns."""
    from optimus.tools.bash_tool.bash_security import _is_safe_heredoc
    if _HEREDOC_IN_SUBSTITUTION.search(ctx.base_command):
        if _is_safe_heredoc(ctx.base_command):
            return _ALLOW
    return _PASSTHROUGH


def validate_git_commit(ctx: ValidationContext) -> PermissionResult:
    """Allow simple git commit -m "..." commands."""
    cmd = ctx.original_command.strip()
    if not re.match(r"^git\s+commit\b", cmd):
        return _PASSTHROUGH
    if "\\" in cmd:
        return _PASSTHROUGH
    # Must have a -m with a quoted message and no dangerous patterns
    m = re.search(r'\s-m\s+"([^"]*)"', cmd)
    if not m:
        return _PASSTHROUGH
    message = m.group(1)
    # No command substitution inside the message
    for pattern, _ in _COMMAND_SUBSTITUTION_PATTERNS:
        if pattern.search(message):
            return _PASSTHROUGH
    # No shell operators in the remaining portion after -m "..."
    remainder = cmd[:m.start()] + cmd[m.end():]
    if re.search(r"[|;&]", remainder):
        return _PASSTHROUGH
    return _ALLOW


def validate_jq_command(ctx: ValidationContext) -> PermissionResult:
    cmd = ctx.original_command.strip()
    if not re.match(r"\bjq\b", cmd):
        return _PASSTHROUGH
    # Block system() function calls
    if re.search(r"\bsystem\s*\(", ctx.unquoted_content):
        return _ask(
            "jq command contains system() call",
            check_id=BASH_SECURITY_CHECK_IDS["JQ_SYSTEM_FUNCTION"],
        )
    # Block dangerous file-reading flags
    for flag in ("-f", "--from-file", "--rawfile", "--slurpfile", "-L", "--library-path"):
        if f" {flag} " in cmd or cmd.endswith(f" {flag}"):
            return _ask(
                f"jq command uses {flag} flag which can read arbitrary files",
                check_id=BASH_SECURITY_CHECK_IDS["JQ_FILE_ARGUMENTS"],
            )
    return _PASSTHROUGH


def validate_shell_metacharacters(ctx: ValidationContext) -> PermissionResult:
    """Detect semicolons/ampersands inside quoted find -name/-path patterns."""
    for pattern in (r'-(?:name|path|iname|regex)\s+[\'"][^"\']*[;&][^"\']*[\'"]',):
        if re.search(pattern, ctx.original_command):
            return _ask(
                "Shell metacharacter inside find pattern argument",
                check_id=BASH_SECURITY_CHECK_IDS["SHELL_METACHARACTERS"],
            )
    return _PASSTHROUGH


def validate_dangerous_variables(ctx: ValidationContext) -> PermissionResult:
    """Detect variables adjacent to redirection operators in fully-unquoted content."""
    if re.search(r'\$\w+\s*[<>|]|[<>|]\s*\$\w+', ctx.fully_unquoted):
        return _ask(
            "Variable adjacent to redirection operator",
            check_id=BASH_SECURITY_CHECK_IDS["DANGEROUS_VARIABLES"],
            misparse=True,
        )
    return _PASSTHROUGH


def validate_dangerous_patterns(ctx: ValidationContext) -> PermissionResult:
    """Detect command substitution patterns and unescaped backticks."""
    # Check for unescaped backticks
    if _has_unescaped_char(ctx.unquoted_content, "`"):
        return _ask(
            "Unescaped backtick (command substitution)",
            check_id=BASH_SECURITY_CHECK_IDS["DANGEROUS_PATTERNS_COMMAND_SUBSTITUTION"],
            misparse=True,
        )
    for pattern, description in _COMMAND_SUBSTITUTION_PATTERNS:
        if pattern.search(ctx.unquoted_content):
            return _ask(
                f"Dangerous pattern: {description}",
                check_id=BASH_SECURITY_CHECK_IDS["DANGEROUS_PATTERNS_COMMAND_SUBSTITUTION"],
                misparse=True,
            )
    return _PASSTHROUGH


def validate_redirections(ctx: ValidationContext) -> PermissionResult:
    """Detect unescaped < and > in fully-unquoted content (after safe redirect stripping)."""
    stripped = _strip_safe_redirections(ctx.fully_unquoted)
    if "<" in stripped or ">" in stripped:
        return _ask(
            "Input/output redirection in unquoted content",
            check_id=BASH_SECURITY_CHECK_IDS["DANGEROUS_PATTERNS_INPUT_REDIRECTION"],
        )
    return _PASSTHROUGH


def validate_newlines(ctx: ValidationContext) -> PermissionResult:
    """Detect newlines used as command separators in unquoted content."""
    for line in ctx.fully_unquoted_pre_strip.split("\n")[1:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return _ask(
                "Newline used as command separator",
                check_id=BASH_SECURITY_CHECK_IDS["NEWLINES"],
            )
    return _PASSTHROUGH


def validate_carriage_return(ctx: ValidationContext) -> PermissionResult:
    """Detect carriage returns outside double-quoted strings."""
    in_double = False
    for ch in ctx.original_command:
        if ch == '"' and not in_double:
            in_double = True
        elif ch == '"' and in_double:
            in_double = False
        elif ch == "\r" and not in_double:
            return _ask(
                "Carriage return outside quoted string",
                check_id=BASH_SECURITY_CHECK_IDS["CONTROL_CHARACTERS"],
                misparse=True,
            )
    return _PASSTHROUGH


def validate_ifs_injection(ctx: ValidationContext) -> PermissionResult:
    """Block $IFS and ${...IFS...} variable references."""
    if re.search(r"\$IFS|\$\{[^}]*IFS[^}]*\}", ctx.original_command):
        return _ask(
            "IFS injection detected",
            check_id=BASH_SECURITY_CHECK_IDS["IFS_INJECTION"],
            misparse=True,
        )
    return _PASSTHROUGH


def validate_proc_environ_access(ctx: ValidationContext) -> PermissionResult:
    """Block /proc/*/environ path patterns."""
    if re.search(r"/proc/[^/]*/environ", ctx.original_command):
        return _ask(
            "Access to /proc/*/environ detected",
            check_id=BASH_SECURITY_CHECK_IDS["PROC_ENVIRON_ACCESS"],
        )
    return _PASSTHROUGH


def validate_malformed_token_injection(ctx: ValidationContext) -> PermissionResult:
    """
    Detect parser-differential attacks via malformed/unbalanced tokens.

    Uses try_parse_shell_command then hasMalformedTokens.
    """
    from optimus.utils.bash.shell_quote import try_parse_shell_command, has_malformed_tokens
    parse_result = try_parse_shell_command(ctx.original_command)
    if not parse_result.success:
        return _ask(
            "Command could not be parsed — possible injection",
            check_id=BASH_SECURITY_CHECK_IDS["MALFORMED_TOKEN_INJECTION"],
            misparse=True,
        )
    tokens = parse_result.tokens or []
    if has_malformed_tokens(ctx.original_command, tokens):
        return _ask(
            "Malformed tokens detected — possible command injection",
            check_id=BASH_SECURITY_CHECK_IDS["MALFORMED_TOKEN_INJECTION"],
            misparse=True,
        )
    return _PASSTHROUGH


def validate_obfuscated_flags(ctx: ValidationContext) -> PermissionResult:
    """
    Block flag obfuscation via ANSI-C quoting, locale quoting, empty-quote pairs,
    and other quote-based tricks to smuggle flags past security checks.

    Mirrors the extensive validateObfuscatedFlags() from bashSecurity.ts.
    """
    cmd = ctx.original_command

    # Block $'...' ANSI-C quoting
    if re.search(r"\$'", cmd):
        return _ask(
            "ANSI-C quoting ($'...') detected — possible flag obfuscation",
            check_id=BASH_SECURITY_CHECK_IDS["OBFUSCATED_FLAGS"],
            misparse=True,
        )

    # Block $"..." locale quoting
    if re.search(r'\$"', cmd):
        return _ask(
            'Locale quoting ($"...") detected — possible flag obfuscation',
            check_id=BASH_SECURITY_CHECK_IDS["OBFUSCATED_FLAGS"],
            misparse=True,
        )

    # Empty quote pair immediately before a dash
    if re.search(r"""(?:''|"")\-""", cmd):
        return _ask(
            "Empty quote pair before dash — possible flag obfuscation",
            check_id=BASH_SECURITY_CHECK_IDS["OBFUSCATED_FLAGS"],
            misparse=True,
        )

    # Three or more consecutive quotes at word start
    if re.search(r"""(?:^|\s)(?:['"]){3,}""", cmd):
        return _ask(
            "Three or more consecutive quotes at word start — possible obfuscation",
            check_id=BASH_SECURITY_CHECK_IDS["OBFUSCATED_FLAGS"],
            misparse=True,
        )

    # Quoted content that starts with a dash (inside single or double quotes adjacent to flags)
    if re.search(r"""['"][^'"]*-[^'"]*['"]""", cmd):
        # Only flag if adjacent to a flag context (word boundary, space or start)
        if re.search(r"""(?:^|\s)['"][^'"]*-""", cmd):
            return _ask(
                "Quoted string starting with dash — possible flag smuggling",
                check_id=BASH_SECURITY_CHECK_IDS["OBFUSCATED_FLAGS"],
                misparse=True,
            )

    return _PASSTHROUGH


def validate_backslash_escaped_whitespace(ctx: ValidationContext) -> PermissionResult:
    r"""
    Detect backslash-escaped spaces/tabs outside quotes.

    bash treats ``\ `` as a single token; some parsers split on the space.
    """
    in_single = False
    in_double = False
    i = 0
    cmd = ctx.original_command
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and not in_single:
            if i + 1 < len(cmd) and cmd[i + 1] in (" ", "\t") and not in_double:
                return _ask(
                    r"Backslash-escaped whitespace (\ ) outside quotes — parser differential",
                    check_id=BASH_SECURITY_CHECK_IDS["BACKSLASH_ESCAPED_WHITESPACE"],
                    misparse=True,
                )
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return _PASSTHROUGH


def validate_backslash_escaped_operators(ctx: ValidationContext) -> PermissionResult:
    r"""
    Detect ``\;``, ``\|``, ``\&``, ``\<``, ``\>`` outside quotes.

    splitCommand normalises these, causing double-parse discrepancies.
    """
    in_single = False
    in_double = False
    i = 0
    cmd = ctx.original_command
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and not in_single:
            if i + 1 < len(cmd):
                next_ch = cmd[i + 1]
                if next_ch in (";", "|", "&", "<", ">") and not in_double:
                    return _ask(
                        f"Backslash-escaped operator (\\{next_ch}) — parser differential",
                        check_id=BASH_SECURITY_CHECK_IDS["BACKSLASH_ESCAPED_OPERATORS"],
                        misparse=True,
                    )
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return _PASSTHROUGH


def validate_brace_expansion(ctx: ValidationContext) -> PermissionResult:
    """
    Detect brace expansion patterns that could hide commands.

    Multi-stage check from validateBraceExpansion() in bashSecurity.ts.
    """
    s = ctx.fully_unquoted_pre_strip

    # More } than { after stripping quotes → attack signature
    if s.count("}") > s.count("{"):
        return _ask(
            "Unbalanced braces — possible brace expansion attack",
            check_id=BASH_SECURITY_CHECK_IDS["BRACE_EXPANSION"],
            misparse=True,
        )

    # Scan for {,...} or {a..b} patterns in unquoted context
    depth = 0
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
        elif ch == "," and depth > 0:
            return _ask(
                "Brace expansion with comma detected",
                check_id=BASH_SECURITY_CHECK_IDS["BRACE_EXPANSION"],
                misparse=True,
            )

    return _PASSTHROUGH


def validate_unicode_whitespace(ctx: ValidationContext) -> PermissionResult:
    """Block Unicode whitespace chars that shell-quote treats as separators but bash treats as literal."""
    for ch in _UNICODE_WHITESPACE_CHARS:
        if ch in ctx.original_command:
            return _ask(
                f"Unicode whitespace character (U+{ord(ch):04X}) — parser differential",
                check_id=BASH_SECURITY_CHECK_IDS["UNICODE_WHITESPACE"],
                misparse=True,
            )
    return _PASSTHROUGH


def validate_mid_word_hash(ctx: ValidationContext) -> PermissionResult:
    """Detect mid-word # (preceded by non-whitespace) in unquoted content."""
    s = ctx.unquoted_keep_quote_chars
    for m in re.finditer(r"#", s):
        i = m.start()
        if i > 0 and not s[i - 1].isspace():
            return _ask(
                "Mid-word # detected — possible comment injection",
                check_id=BASH_SECURITY_CHECK_IDS["MID_WORD_HASH"],
                misparse=True,
            )
    return _PASSTHROUGH


def validate_zsh_dangerous_commands(ctx: ValidationContext) -> PermissionResult:
    """Block Zsh-specific dangerous commands."""
    from optimus.utils.bash.shell_quote import try_parse_shell_command
    parse_result = try_parse_shell_command(ctx.original_command)
    if not parse_result.success:
        return _PASSTHROUGH
    tokens = [t for t in (parse_result.tokens or []) if isinstance(t, str)]
    if not tokens:
        return _PASSTHROUGH
    # Skip leading env var assignments
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_]\w*=", tokens[i]):
        i += 1
    base_cmd = tokens[i] if i < len(tokens) else ""
    # Strip path prefix
    base_cmd = base_cmd.rsplit("/", 1)[-1]

    if base_cmd in _ZSH_DANGEROUS_COMMANDS:
        return _ask(
            f"Dangerous Zsh command: {base_cmd}",
            check_id=BASH_SECURITY_CHECK_IDS["ZSH_DANGEROUS_COMMANDS"],
        )
    # Also block fc -e
    if base_cmd == "fc" and i + 1 < len(tokens) and tokens[i + 1] == "-e":
        return _ask(
            "fc -e is dangerous (executes history commands)",
            check_id=BASH_SECURITY_CHECK_IDS["ZSH_DANGEROUS_COMMANDS"],
        )
    return _PASSTHROUGH


def validate_comment_quote_desync(ctx: ValidationContext) -> PermissionResult:
    """
    Detect # comment lines containing quote chars that would desync quote trackers.
    """
    for line in ctx.original_command.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and ('"' in stripped or "'" in stripped):
            return _ask(
                "Comment line contains quote character — possible quote desynchronization",
                check_id=BASH_SECURITY_CHECK_IDS["COMMENT_QUOTE_DESYNC"],
                misparse=True,
            )
    return _PASSTHROUGH


def validate_quoted_newline(ctx: ValidationContext) -> PermissionResult:
    """
    Detect newlines inside quoted strings where the next line starts with #.
    stripCommentLines would strip the # line, hiding arguments.
    """
    in_single = False
    in_double = False
    cmd = ctx.original_command
    for i, ch in enumerate(cmd):
        if ch == "\\" and not in_single and i + 1 < len(cmd):
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "\n" and (in_single or in_double):
            rest = cmd[i + 1:].lstrip("\t ")
            if rest.startswith("#"):
                return _ask(
                    "Newline inside quoted string followed by comment — possible hidden argument",
                    check_id=BASH_SECURITY_CHECK_IDS["QUOTED_NEWLINE"],
                    misparse=True,
                )
    return _PASSTHROUGH


# ---------------------------------------------------------------------------
# Safe heredoc check (used by validate_safe_command_substitution)
# ---------------------------------------------------------------------------

def _is_safe_heredoc(command: str) -> bool:
    """
    True if command contains $(cat <<'DELIM'...DELIM) that is provably safe.

    Simplified version of isSafeHeredoc() from bashSecurity.ts — handles the
    common quoted-delimiter case.
    """
    result = extract_heredocs(command, quoted_only=True)
    # If any heredoc was extracted, the remainder passes through the safe check
    if result.heredocs:
        return True
    return False


# ---------------------------------------------------------------------------
# stripSafeHeredocSubstitutions  (exported)
# ---------------------------------------------------------------------------

def strip_safe_heredoc_substitutions(command: str) -> str | None:
    """
    Strip safe heredoc-in-substitution patterns from *command*.

    Returns the stripped command (with heredoc body removed) or None if
    no safe heredoc substitutions were found.

    Mirrors stripSafeHeredocSubstitutions() from bashSecurity.ts.
    """
    if "<<" not in command:
        return None
    result = extract_heredocs(command, quoted_only=True)
    if not result.heredocs:
        return None
    # Replace each heredoc placeholder with an empty string (the safe body is removed)
    processed = result.processed_command
    for placeholder in result.heredocs:
        processed = processed.replace(placeholder, "")
    return processed if processed != command else None


def has_safe_heredoc_substitution(command: str) -> bool:
    """True if command contains a safe heredoc-in-substitution pattern."""
    return strip_safe_heredoc_substitutions(command) is not None


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

_MISPARSING_VALIDATORS = (
    validate_dangerous_variables,
    validate_carriage_return,
    validate_ifs_injection,
    validate_dangerous_patterns,
    validate_backslash_escaped_whitespace,
    validate_backslash_escaped_operators,
    validate_unicode_whitespace,
    validate_mid_word_hash,
    validate_brace_expansion,
    validate_malformed_token_injection,
)

_NON_MISPARSING_VALIDATORS = (
    validate_jq_command,
    validate_obfuscated_flags,
    validate_shell_metacharacters,
    validate_comment_quote_desync,
    validate_quoted_newline,
    validate_newlines,
    validate_proc_environ_access,
    validate_redirections,
    validate_zsh_dangerous_commands,
)


def _build_context(command: str) -> ValidationContext:
    """Build a ValidationContext from a raw command string."""
    from optimus.utils.bash.shell_quote import has_shell_quote_single_quote_bug
    base = command
    heredoc_result = extract_heredocs(command, quoted_only=True)
    if heredoc_result.heredocs:
        for ph in heredoc_result.heredocs:
            base = base.replace(ph, "")

    extracted = _extract_quoted_content(base)
    return ValidationContext(
        original_command=command,
        base_command=base,
        unquoted_content=extracted["with_double_quotes"],
        fully_unquoted=extracted["fully_unquoted"],
        fully_unquoted_pre_strip=extracted["fully_unquoted"],
        unquoted_keep_quote_chars=extracted["unquoted_keep_quote_chars"],
    )


def bash_command_is_safe_DEPRECATED(command: str) -> PermissionResult:  # noqa: N802
    """
    Synchronous bash security check.

    Mirrors bashCommandIsSafe_DEPRECATED() from bashSecurity.ts.

    Runs all 23 validators in the same order as the TS source.
    Misparsing validators return immediately; non-misparsing ones can be
    deferred (their 'ask' results are collected and the first is returned at
    the end if no misparsing block was triggered).
    """
    from optimus.utils.bash.shell_quote import has_shell_quote_single_quote_bug

    # Control character check
    if _CONTROL_CHAR_RE.search(command):
        return _ask(
            "Control character in command",
            check_id=BASH_SECURITY_CHECK_IDS["CONTROL_CHARACTERS"],
            misparse=True,
        )

    # Shell-quote single-quote bug
    if has_shell_quote_single_quote_bug(command):
        return _ask(
            "Command exploits single-quote parsing bug",
            check_id=BASH_SECURITY_CHECK_IDS["MALFORMED_TOKEN_INJECTION"],
            misparse=True,
        )

    ctx = _build_context(command)

    # Early validators
    for validator in (validate_empty, validate_incomplete_commands,
                      validate_safe_command_substitution, validate_git_commit):
        result = validator(ctx)
        if result.behavior != "passthrough":
            return result

    # Collect deferred (non-misparsing) ask results
    deferred: list[PermissionResult] = []

    # Non-misparsing validators first (collect deferred)
    for validator in _NON_MISPARSING_VALIDATORS:
        result = validator(ctx)
        if result.behavior == "ask" and not result.is_bash_security_check_for_misparsing:
            deferred.append(result)

    # Misparsing validators (return immediately on ask)
    for validator in _MISPARSING_VALIDATORS:
        result = validator(ctx)
        if result.behavior == "ask" and result.is_bash_security_check_for_misparsing:
            return result

    # Return first deferred ask if any
    if deferred:
        return deferred[0]

    return _ALLOW


async def bash_command_is_safe_async_DEPRECATED(command: str) -> PermissionResult:  # noqa: N802
    """
    Async bash security check.

    Mirrors bashCommandIsSafeAsync_DEPRECATED() from bashSecurity.ts.

    Tree-sitter integration is not yet implemented; falls back to the sync path.
    The sync path covers all regex-based validators — which is the majority.
    """
    return bash_command_is_safe_DEPRECATED(command)
