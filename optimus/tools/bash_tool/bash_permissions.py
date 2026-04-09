"""
Bash tool permission checking.

Faithful Python port of src/tools/BashTool/bashPermissions.ts.

Key exported functions:
  - bash_tool_has_permission(input, context, ...)  → PermissionResult (async)
  - bash_tool_check_permission(input, context, ...) → PermissionResult
  - bash_tool_check_exact_match_permission(input, context) → PermissionResult
  - check_command_and_suggest_rules(input, context, ...) → PermissionResult (async)
  - strip_safe_wrappers(command) → str
  - strip_all_leading_env_vars(command, blocklist?) → str
  - strip_wrappers_from_argv(argv) → list[str]
  - get_simple_command_prefix(command) → str | None
  - get_first_word_prefix(command) → str | None
  - is_normalized_git_command(command) → bool
  - is_normalized_cd_command(command) → bool
  - command_has_any_cd(command) → bool
  - speculative classifier helpers

Security notes:
  - SAFE_ENV_VARS: never add PATH, LD_PRELOAD, LD_LIBRARY_PATH, DYLD_*, PYTHONPATH,
    NODE_PATH, CLASSPATH, RUBYLIB, GOFLAGS, RUSTFLAGS, NODE_OPTIONS, HOME, TMPDIR,
    SHELL, BASH_ENV.
  - strip_safe_wrappers uses [ \\t]+ not \\s+ (\\s would match \\n/\\r which are
    command separators; matching across a newline would strip the wrapper from one
    line and leave a different command on the next line for bash to execute).
  - ENV_VAR_PATTERN trailing whitespace MUST be [ \\t]+ (horizontal only), NOT \\s+.
"""
from __future__ import annotations

import asyncio
import os
import re
from asyncio import Future
from typing import Any, Callable

from optimus.tool import ToolPermissionContext, ToolUseContext
from optimus.types.permissions import (
    ClassifierResult,
    PendingClassifierCheck,
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionDecisionReason,
    PermissionDenyDecision,
    PermissionPassthroughDecision,
    PermissionResult,
    PermissionRule,
    PermissionRuleValue,
)
from optimus.utils.bash.commands import (
    extract_output_redirections,
    split_command_DEPRECATED as split_command,
)
from optimus.utils.bash.shell_quote import try_parse_shell_command
from optimus.utils.cwd import get_cwd
from optimus.utils.env_utils import is_env_truthy
from optimus.utils.permissions.bash_classifier import (
    classify_bash_command,
    get_bash_prompt_allow_descriptions,
    get_bash_prompt_ask_descriptions,
    get_bash_prompt_deny_descriptions,
    is_classifier_permissions_enabled,
)
from optimus.utils.permissions.permission_rule_parser import (
    permission_rule_value_to_string,
)
from optimus.utils.permissions.permission_update import extract_rules
from optimus.utils.permissions.permission_update_schema import PermissionUpdate
from optimus.utils.permissions.permissions import (
    create_permission_request_message,
    get_rule_by_contents_for_tool,
)
from optimus.utils.permissions.shell_rule_matching import (
    match_wildcard_pattern as _shared_match_wildcard_pattern,
    parse_permission_rule,
    permission_rule_extract_prefix as _shared_permission_rule_extract_prefix,
    suggestion_for_exact_command as _shared_suggestion_for_exact_command,
    suggestion_for_prefix as _shared_suggestion_for_prefix,
)
from optimus.tools.bash_tool.bash_security import (
    bash_command_is_safe_async_DEPRECATED as bash_command_is_safe_async,
    strip_safe_heredoc_substitutions,
)

# Deferred imports to avoid circular dependencies
# These are imported lazily on first use.
_bash_tool_module: Any = None


def _get_bash_tool() -> Any:
    global _bash_tool_module
    if _bash_tool_module is None:
        from optimus.tools.bash_tool import bash_tool as _bt
        _bash_tool_module = _bt
    return _bash_tool_module


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CC-643: Cap to prevent exponential subcommand fanout on complex expressions.
MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50

# GH#11380: Cap suggestions for compound commands.
MAX_SUGGESTED_RULES_FOR_COMPOUND = 5

# Env var assignment prefix pattern (VAR=value). Used across three while-loops.
_ENV_VAR_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# SECURITY: allowlist for timeout flag VALUES.
_TIMEOUT_FLAG_VALUE_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")

# BINARY_HIJACK_VARS: env vars that make a different binary run.
BINARY_HIJACK_VARS = re.compile(r"^(LD_|DYLD_|PATH$)")

# ---------------------------------------------------------------------------
# Safe environment variable sets
# ---------------------------------------------------------------------------

SAFE_ENV_VARS: frozenset[str] = frozenset([
    # Go - build/runtime settings only
    "GOEXPERIMENT", "GOOS", "GOARCH", "CGO_ENABLED", "GO111MODULE",
    # Rust - logging/debugging only
    "RUST_BACKTRACE", "RUST_LOG",
    # Node - environment name only (not NODE_OPTIONS!)
    "NODE_ENV",
    # Python - behavior flags only (not PYTHONPATH!)
    "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
    # Pytest - test configuration
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_DEBUG",
    # API keys and authentication
    "ANTHROPIC_API_KEY",
    # Locale and character encoding
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_TIME", "CHARSET",
    # Terminal and display
    "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR", "TZ",
    # Color configuration for various tools
    "LS_COLORS", "LSCOLORS", "GREP_COLOR", "GREP_COLORS", "GCC_COLORS",
    # Display formatting
    "TIME_STYLE", "BLOCK_SIZE", "BLOCKSIZE",
])

# ANT-ONLY: These are stripped only when USER_TYPE === 'ant'.
# SECURITY: MUST NEVER be enabled for external users.
# These include DOCKER_HOST (redirects Docker daemon) and KUBECONFIG
# (controls which cluster kubectl talks to) — stripping them defeats
# prefix-based permission restrictions.
ANT_ONLY_SAFE_ENV_VARS: frozenset[str] = frozenset([
    "KUBECONFIG", "DOCKER_HOST",
    "AWS_PROFILE", "CLOUDSDK_CORE_PROJECT", "CLUSTER",
    "COO_CLUSTER", "COO_CLUSTER_NAME", "COO_NAMESPACE", "COO_LAUNCH_YAML_DRY_RUN",
    "SKIP_NODE_VERSION_CHECK", "EXPECTTEST_ACCEPT", "CI", "GIT_LFS_SKIP_SMUDGE",
    "CUDA_VISIBLE_DEVICES", "JAX_PLATFORMS",
    "COLUMNS", "TMUX",
    "POSTGRESQL_VERSION", "FIRESTORE_EMULATOR_HOST", "HARNESS_QUIET",
    "TEST_CROSSCHECK_LISTS_MATCH_UPDATE", "DBT_PER_DEVELOPER_ENVIRONMENTS",
    "STATSIG_FORD_DB_CHECKS",
    "ANT_ENVIRONMENT", "ANT_SERVICE", "MONOREPO_ROOT_DIR",
    "PYENV_VERSION",
    "PGPASSWORD", "GH_TOKEN", "GROWTHBOOK_API_KEY",
])

# Bare-prefix suggestions like bash:* or sh:* would allow arbitrary code.
# Wrapper suggestions like env:* or sudo:* would do the same.
_BARE_SHELL_PREFIXES: frozenset[str] = frozenset([
    "sh", "bash", "zsh", "fish", "csh", "tcsh", "ksh", "dash",
    "cmd", "powershell", "pwsh",
    # wrappers that exec their args as a command
    "env", "xargs",
    # SECURITY: checkSemantics (ast.ts) strips these wrappers. Suggesting
    # Bash(nice:*) would be ≈ Bash(*). Block these from ever being suggested.
    "nice", "stdbuf", "nohup", "timeout", "time",
    # privilege escalation
    "sudo", "doas", "pkexec",
])


# ---------------------------------------------------------------------------
# Shell comment line stripping
# ---------------------------------------------------------------------------

def _strip_comment_lines(command: str) -> str:
    """
    Strip full-line comments from a command.
    Only strips lines where the entire line is a comment, not inline comments.
    """
    lines = command.split("\n")
    non_comment_lines = [
        line for line in lines
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]
    if not non_comment_lines:
        return command
    return "\n".join(non_comment_lines)


# ---------------------------------------------------------------------------
# stripSafeWrappers
# ---------------------------------------------------------------------------

def strip_safe_wrappers(command: str) -> str:
    """
    Strip safe wrapper commands (timeout, time, nice, nohup) and safe env vars
    from the front of a command for permission-rule matching.

    SECURITY: Uses [ \\t]+ not \\s+ — \\s matches \\n/\\r which are command
    separators in bash. Matching across a newline would strip the wrapper from
    one line and leave a different command on the next line.

    SECURITY: `(?:--[ \\t]+)?` consumes the wrapper's own `--` so
    `nohup -- rm -- -/../foo` strips to `rm -- -/../foo`.
    """
    # SAFE_WRAPPER_PATTERNS: each strips a specific wrapper invocation.
    # Flag VALUES use allowlist [A-Za-z0-9_.+-] (signals are TERM/KILL/9,
    # durations are 5/5s/10.5). Previously [^ \\t]+ matched $ ( ) ` | ; & —
    # `timeout -k$(id) 10 ls` stripped to `ls`, matched Bash(ls:*), while
    # bash expanded $(id) during word splitting BEFORE timeout ran.
    _SAFE_WRAPPER_PATTERNS = [
        re.compile(
            r"^timeout[ \t]+(?:(?:--(?:foreground|preserve-status|verbose)"
            r"|--(?:kill-after|signal)=[A-Za-z0-9_.+-]+"
            r"|--(?:kill-after|signal)[ \t]+[A-Za-z0-9_.+-]+"
            r"|-v|-[ks][ \t]+[A-Za-z0-9_.+-]+"
            r"|-[ks][A-Za-z0-9_.+-]+)[ \t]+)*"
            r"(?:--[ \t]+)?\d+(?:\.\d+)?[smhd]?[ \t]+"
        ),
        re.compile(r"^time[ \t]+(?:--[ \t]+)?"),
        # nice: matches bare `nice cmd`, `nice -n N cmd`, `nice -N cmd`
        re.compile(r"^nice(?:[ \t]+-n[ \t]+-?\d+|[ \t]+-\d+)?[ \t]+(?:--[ \t]+)?"),
        # stdbuf: fused short flags only (-o0, -eL).
        re.compile(r"^stdbuf(?:[ \t]+-[ioe][LN0-9]+)+[ \t]+(?:--[ \t]+)?"),
        re.compile(r"^nohup[ \t]+(?:--[ \t]+)?"),
    ]

    # Pattern for environment variables in Phase 1 (safe-list gated):
    # Only matches unquoted values with safe characters (no $(), `, $var, ;|&).
    # Trailing whitespace MUST be [ \\t]+ (horizontal only), NOT \\s+.
    _ENV_VAR_PATTERN = re.compile(
        r"^([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./:-]+)[ \t]+"
    )

    stripped = command

    # Phase 1: Strip leading env vars and comments only.
    previous = ""
    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        m = _ENV_VAR_PATTERN.match(stripped)
        if m:
            var_name = m.group(1)
            is_ant_only_safe = (
                os.environ.get("USER_TYPE") == "ant"
                and var_name in ANT_ONLY_SAFE_ENV_VARS
            )
            if var_name in SAFE_ENV_VARS or is_ant_only_safe:
                stripped = _ENV_VAR_PATTERN.sub("", stripped, count=1)

    # Phase 2: Strip wrapper commands and comments only. Do NOT strip env vars.
    # Wrapper commands use execvp to run their arguments, so VAR=val after a
    # wrapper is treated as the COMMAND to execute, not an env var assignment.
    # Stripping env vars here would create a mismatch (HackerOne #3543050).
    previous = ""
    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        for pattern in _SAFE_WRAPPER_PATTERNS:
            stripped = pattern.sub("", stripped, count=1)

    return stripped.strip()


# ---------------------------------------------------------------------------
# skipTimeoutFlags — parse timeout's GNU flags
# ---------------------------------------------------------------------------

def _skip_timeout_flags(argv: list[str]) -> int:
    """
    Parse timeout's GNU flags (long + short, fused + space-separated) and
    return the argv index of the DURATION token, or -1 if flags are unparseable.

    Mirrors skipTimeoutFlags() from bashPermissions.ts.
    """
    i = 1
    while i < len(argv):
        arg = argv[i]
        next_arg = argv[i + 1] if i + 1 < len(argv) else None
        if arg in ("--foreground", "--preserve-status", "--verbose"):
            i += 1
        elif re.match(r"^--(?:kill-after|signal)=[A-Za-z0-9_.+-]+$", arg):
            i += 1
        elif arg in ("--kill-after", "--signal") and next_arg and _TIMEOUT_FLAG_VALUE_RE.match(next_arg):
            i += 2
        elif arg == "--":
            i += 1
            break  # end-of-options marker
        elif arg.startswith("--"):
            return -1
        elif arg == "-v":
            i += 1
        elif arg in ("-k", "-s") and next_arg and _TIMEOUT_FLAG_VALUE_RE.match(next_arg):
            i += 2
        elif re.match(r"^-[ks][A-Za-z0-9_.+-]+$", arg):
            i += 1
        elif arg.startswith("-"):
            return -1
        else:
            break
    return i


# ---------------------------------------------------------------------------
# stripWrappersFromArgv
# ---------------------------------------------------------------------------

def strip_wrappers_from_argv(argv: list[str]) -> list[str]:
    """
    Argv-level counterpart to strip_safe_wrappers. Strips the same wrapper
    commands (timeout, time, nice, nohup) from AST-derived argv.

    SECURITY: Consume optional `--` after wrapper options, matching what the
    wrapper does. Otherwise `['nohup','--','rm','--','-/../foo']` yields `--`
    as baseCmd and skips path validation.

    KEEP IN SYNC with SAFE_WRAPPER_PATTERNS in strip_safe_wrappers.
    """
    a = argv
    while True:
        if not a:
            return a
        if a[0] in ("time", "nohup"):
            a = a[2:] if len(a) > 1 and a[1] == "--" else a[1:]
        elif a[0] == "timeout":
            i = _skip_timeout_flags(a)
            if i < 0 or i >= len(a) or not re.match(r"^\d+(?:\.\d+)?[smhd]?$", a[i]):
                return a
            a = a[i + 1:]
        elif a[0] == "nice" and len(a) > 2 and a[1] == "-n" and re.match(r"^-?\d+$", a[2]):
            a = a[4:] if len(a) > 3 and a[3] == "--" else a[3:]
        else:
            return a


# ---------------------------------------------------------------------------
# stripAllLeadingEnvVars
# ---------------------------------------------------------------------------

def strip_all_leading_env_vars(command: str, blocklist: re.Pattern[str] | None = None) -> str:
    """
    Strip ALL leading env var prefixes from a command, regardless of whether
    the var name is in the safe-list.

    Used for deny/ask rule matching: a denied command should stay blocked even
    if prefixed with arbitrary env vars like `FOO=bar denied_command`.

    SECURITY: Uses a broader value pattern than strip_safe_wrappers. The value
    pattern excludes only actual shell injection characters ($, backtick, ;, |,
    &, parens, redirects, quotes, backslash) and whitespace.

    Trailing whitespace MUST be [ \\t]+ (horizontal only), NOT \\s+.
    """
    # Broader value pattern for deny-rule stripping:
    # - Standard assignment (FOO=bar), append (FOO+=bar), array (FOO[0]=bar)
    # - Single-quoted values: '[^'\\n\\r]*'
    # - Double-quoted values with backslash escapes: "(?:\\\\.|[^"$`\\\\\\n\\r])*"
    # - Unquoted values: excludes shell metacharacters
    # - Concatenated segments: FOO='x'y"z"
    # Note: $ is excluded to block $(cmd), ${var}, $((expr)). CodeQL #671.
    _ENV_VAR_BROAD_RE = re.compile(
        r"^([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?)\+?="
        r"""(?:'[^'\n\r]*'|"(?:\\.|[^"$`\\\n\r])*"|\\.|[^ \t\n\r$`;|&()<>\\\\'"])*"""
        r"[ \t]+"
    )

    stripped = command
    previous = ""

    while stripped != previous:
        previous = stripped
        stripped = _strip_comment_lines(stripped)
        m = _ENV_VAR_BROAD_RE.match(stripped)
        if not m:
            continue
        if blocklist and blocklist.search(m.group(1)):
            break
        stripped = stripped[m.end():]

    return stripped.strip()


# ---------------------------------------------------------------------------
# Permission rule helpers (delegates to shared implementations)
# ---------------------------------------------------------------------------

def permission_rule_extract_prefix(permission_rule: str) -> str | None:
    """Extract prefix from legacy :* syntax. Delegates to shared implementation."""
    return _shared_permission_rule_extract_prefix(permission_rule)


def match_wildcard_pattern(pattern: str, command: str) -> bool:
    """Match a command against a wildcard pattern (case-sensitive for Bash)."""
    return _shared_match_wildcard_pattern(pattern, command)


# bash_permission_rule = parse_permission_rule (exported alias)
bash_permission_rule = parse_permission_rule


# ---------------------------------------------------------------------------
# getSimpleCommandPrefix
# ---------------------------------------------------------------------------

def get_simple_command_prefix(command: str) -> str | None:
    """
    Extract a stable command prefix (command + subcommand) from a raw command string.

    Skips leading env var assignments only if they are in SAFE_ENV_VARS (or
    ANT_ONLY_SAFE_ENV_VARS for ant users). Returns None if a non-safe env var
    is encountered, or if the second token doesn't look like a subcommand.

    Examples:
      'git commit -m "fix typo"' → 'git commit'
      'NODE_ENV=prod npm run build' → 'npm run'
      'MY_VAR=val npm run build' → None
      'ls -la' → None
      'cat file.txt' → None
    """
    tokens = [t for t in command.strip().split() if t]
    if not tokens:
        return None

    i = 0
    while i < len(tokens) and _ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split("=")[0]
        is_ant_only_safe = (
            os.environ.get("USER_TYPE") == "ant"
            and var_name in ANT_ONLY_SAFE_ENV_VARS
        )
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1

    remaining = tokens[i:]
    if len(remaining) < 2:
        return None
    subcmd = remaining[1]
    # Second token must look like a subcommand (e.g., "commit", "run", "compose"),
    # not a flag (-rf), filename (file.txt), path (/tmp), URL, or number (755).
    if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", subcmd):
        return None
    return " ".join(remaining[:2])


# ---------------------------------------------------------------------------
# getFirstWordPrefix
# ---------------------------------------------------------------------------

def get_first_word_prefix(command: str) -> str | None:
    """
    UI-only fallback: extract the first word alone when get_simple_command_prefix
    declines. Reuses the same SAFE_ENV_VARS gate.

    Deliberately not used by suggestion_for_exact_command: a backend-suggested
    `Bash(rm:*)` is too broad, but as an editable starting point it's expected.
    """
    tokens = [t for t in command.strip().split() if t]

    i = 0
    while i < len(tokens) and _ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split("=")[0]
        is_ant_only_safe = (
            os.environ.get("USER_TYPE") == "ant"
            and var_name in ANT_ONLY_SAFE_ENV_VARS
        )
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1

    if i >= len(tokens):
        return None
    cmd = tokens[i]
    # Same shape check as subcommand regex in get_simple_command_prefix.
    if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", cmd):
        return None
    if cmd in _BARE_SHELL_PREFIXES:
        return None
    return cmd


# ---------------------------------------------------------------------------
# Heredoc prefix extraction
# ---------------------------------------------------------------------------

def _extract_prefix_before_heredoc(command: str) -> str | None:
    """
    If the command contains a heredoc (<<), extract the command prefix before it.
    Returns the first word(s) before the heredoc operator as a stable prefix,
    or None if the command doesn't contain a heredoc.

    Examples:
      'git commit -m "$(cat <<\\'EOF\\'\\n...\\nEOF\\n)"' → 'git commit'
      'cat <<EOF\\nhello\\nEOF' → 'cat'
      'echo hello' → None (no heredoc)
    """
    if "<<" not in command:
        return None

    idx = command.index("<<")
    if idx <= 0:
        return None

    before = command[:idx].strip()
    if not before:
        return None

    prefix = get_simple_command_prefix(before)
    if prefix:
        return prefix

    # Fallback: skip safe env var assignments and take up to 2 tokens.
    tokens = [t for t in before.split() if t]
    i = 0
    while i < len(tokens) and _ENV_VAR_ASSIGN_RE.match(tokens[i]):
        var_name = tokens[i].split("=")[0]
        is_ant_only_safe = (
            os.environ.get("USER_TYPE") == "ant"
            and var_name in ANT_ONLY_SAFE_ENV_VARS
        )
        if var_name not in SAFE_ENV_VARS and not is_ant_only_safe:
            return None
        i += 1
    if i >= len(tokens):
        return None
    result = " ".join(tokens[i:i + 2])
    return result or None


# ---------------------------------------------------------------------------
# Permission update suggestion helpers
# ---------------------------------------------------------------------------

def _tool_name() -> str:
    """Return the canonical BashTool name."""
    return "Bash"


def _suggestion_for_exact_command(command: str) -> list[PermissionUpdate]:
    """
    Suggest a permission update for an exact command.

    Heredoc commands → stable prefix rule.
    Multiline without heredoc → first-line prefix rule.
    Single-line → try 2-word prefix, fall back to exact match.
    """
    heredoc_prefix = _extract_prefix_before_heredoc(command)
    if heredoc_prefix:
        return _shared_suggestion_for_prefix(_tool_name(), heredoc_prefix)

    if "\n" in command:
        first_line = command.split("\n")[0].strip()
        if first_line:
            return _shared_suggestion_for_prefix(_tool_name(), first_line)

    prefix = get_simple_command_prefix(command)
    if prefix:
        return _shared_suggestion_for_prefix(_tool_name(), prefix)

    return _shared_suggestion_for_exact_command(_tool_name(), command)


def _suggestion_for_prefix(prefix: str) -> list[PermissionUpdate]:
    return _shared_suggestion_for_prefix(_tool_name(), prefix)


# ---------------------------------------------------------------------------
# filterRulesByContentsMatchingInput
# ---------------------------------------------------------------------------

def _filter_rules_by_contents_matching_input(
    command: str,
    rules: dict[str, PermissionRule],
    match_mode: str,  # 'exact' | 'prefix'
    strip_all_env_vars: bool = False,
    skip_compound_check: bool = False,
) -> list[PermissionRule]:
    """
    Filter permission rules to those matching the given command.

    Mirrors filterRulesByContentsMatchingInput() from bashPermissions.ts.

    SECURITY:
    - Deny/ask rules use aggressive env var stripping.
    - Wildcards must NOT match in 'exact' mode.
    - Prefix rules must NOT match compound commands (prevents cd:* matching
      "cd /path && python3 evil.py").
    """
    command = command.strip()

    # Strip output redirections for permission matching.
    redirection_result = extract_output_redirections(command)
    command_without_redirections = redirection_result.command_without_redirections

    # For exact matching, try both original and without redirections.
    # For prefix matching, only use without redirections.
    if match_mode == "exact":
        commands_for_matching = [command, command_without_redirections]
    else:
        commands_for_matching = [command_without_redirections]

    # Strip safe wrapper commands and env vars for matching.
    commands_to_try: list[str] = []
    for cmd in commands_for_matching:
        stripped = strip_safe_wrappers(cmd)
        if stripped != cmd:
            commands_to_try.extend([cmd, stripped])
        else:
            commands_to_try.append(cmd)

    # SECURITY: For deny/ask rules, also try stripping ALL leading env vars.
    # Iteratively apply until fixed-point to handle multi-layer interleaving
    # like `nohup FOO=bar timeout 5 claude`.
    if strip_all_env_vars:
        seen: set[str] = set(commands_to_try)
        start_idx = 0
        while start_idx < len(commands_to_try):
            end_idx = len(commands_to_try)
            for i in range(start_idx, end_idx):
                cmd = commands_to_try[i]
                env_stripped = strip_all_leading_env_vars(cmd)
                if env_stripped not in seen:
                    commands_to_try.append(env_stripped)
                    seen.add(env_stripped)
                wrapper_stripped = strip_safe_wrappers(cmd)
                if wrapper_stripped not in seen:
                    commands_to_try.append(wrapper_stripped)
                    seen.add(wrapper_stripped)
            start_idx = end_idx

    # Precompute compound-command status for each candidate to avoid re-parsing
    # inside the rule filter loop.
    is_compound: dict[str, bool] = {}
    if match_mode == "prefix" and not skip_compound_check:
        for cmd in commands_to_try:
            if cmd not in is_compound:
                is_compound[cmd] = len(split_command(cmd)) > 1

    result: list[PermissionRule] = []
    for rule_content, rule in rules.items():
        bash_rule = bash_permission_rule(rule_content)

        def _matches(cmd_to_match: str) -> bool:
            if bash_rule.type == "exact":
                return bash_rule.command == cmd_to_match
            elif bash_rule.type == "prefix":
                if match_mode == "exact":
                    return bash_rule.prefix == cmd_to_match
                else:  # prefix mode
                    # SECURITY: Don't allow prefix rules to match compound commands.
                    if is_compound.get(cmd_to_match, False):
                        return False
                    if cmd_to_match == bash_rule.prefix:
                        return True
                    if cmd_to_match.startswith(bash_rule.prefix + " "):
                        return True
                    # Also match "xargs <prefix>" for bare xargs.
                    xargs_prefix = "xargs " + bash_rule.prefix
                    if cmd_to_match == xargs_prefix:
                        return True
                    return cmd_to_match.startswith(xargs_prefix + " ")
            elif bash_rule.type == "wildcard":
                # SECURITY: In exact match mode, wildcards must NOT match.
                if match_mode == "exact":
                    return False
                # SECURITY: Don't allow wildcard rules to match compound commands.
                if is_compound.get(cmd_to_match, False):
                    return False
                return match_wildcard_pattern(bash_rule.pattern, cmd_to_match)
            return False

        if any(_matches(cmd) for cmd in commands_to_try):
            result.append(rule)

    return result


# ---------------------------------------------------------------------------
# matchingRulesForInput
# ---------------------------------------------------------------------------

def _matching_rules_for_input(
    command: str,
    tool_permission_context: ToolPermissionContext,
    match_mode: str,
    skip_compound_check: bool = False,
) -> tuple[list[PermissionRule], list[PermissionRule], list[PermissionRule]]:
    """
    Returns (matching_deny_rules, matching_ask_rules, matching_allow_rules).
    SECURITY: Deny/ask rules use aggressive env var stripping.
    """
    bt = _get_bash_tool()
    bash_tool = getattr(bt, "BashTool", None) or getattr(bt, "bash_tool_instance", None)

    deny_rules = get_rule_by_contents_for_tool(tool_permission_context, bash_tool, "deny")
    ask_rules = get_rule_by_contents_for_tool(tool_permission_context, bash_tool, "ask")
    allow_rules = get_rule_by_contents_for_tool(tool_permission_context, bash_tool, "allow")

    matching_deny = _filter_rules_by_contents_matching_input(
        command, deny_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )
    matching_ask = _filter_rules_by_contents_matching_input(
        command, ask_rules, match_mode,
        strip_all_env_vars=True, skip_compound_check=True,
    )
    matching_allow = _filter_rules_by_contents_matching_input(
        command, allow_rules, match_mode,
        skip_compound_check=skip_compound_check,
    )

    return matching_deny, matching_ask, matching_allow


# ---------------------------------------------------------------------------
# bashToolCheckExactMatchPermission
# ---------------------------------------------------------------------------

def bash_tool_check_exact_match_permission(
    command: str,
    tool_permission_context: ToolPermissionContext,
) -> PermissionResult:
    """
    Checks if the command is an exact match for a permission rule.

    Returns deny/ask/allow/passthrough.
    """
    command = command.strip()
    matching_deny, matching_ask, matching_allow = _matching_rules_for_input(
        command, tool_permission_context, "exact"
    )

    # 1. Deny if exact command was denied
    if matching_deny:
        return PermissionDenyDecision(
            message=f"Permission to use Bash with command {command} has been denied.",
            decision_reason={"type": "rule", "rule": matching_deny[0]},
        )

    # 2. Ask if exact command was in ask rules
    if matching_ask:
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name()),
            decision_reason={"type": "rule", "rule": matching_ask[0]},
        )

    # 3. Allow if exact command was allowed
    if matching_allow:
        return PermissionAllowDecision(
            updated_input={"command": command},
            decision_reason={"type": "rule", "rule": matching_allow[0]},
        )

    # 4. Passthrough
    decision_reason: PermissionDecisionReason = {
        "type": "other",
        "reason": "This command requires approval",
    }
    return PermissionPassthroughDecision(
        message=create_permission_request_message(_tool_name(), decision_reason),
        decision_reason=decision_reason,
        suggestions=_suggestion_for_exact_command(command),
    )


# ---------------------------------------------------------------------------
# bashToolCheckPermission
# ---------------------------------------------------------------------------

def bash_tool_check_permission(
    command: str,
    tool_permission_context: ToolPermissionContext,
    compound_command_has_cd: bool = False,
    ast_command: Any = None,
) -> PermissionResult:
    """
    Checks a single (sub)command against all permission rules, path constraints,
    sed constraints, mode checks, and read-only validation.

    Mirrors bashToolCheckPermission() from bashPermissions.ts.
    """
    command = command.strip()

    # 1. Check exact match first
    exact_match_result = bash_tool_check_exact_match_permission(
        command, tool_permission_context
    )

    # 1a. Deny/ask if exact command has a rule
    if exact_match_result.behavior in ("deny", "ask"):
        return exact_match_result

    # 2. Find all matching rules (prefix or exact)
    # SECURITY: Check deny/ask rules BEFORE path constraints.
    skip_compound = ast_command is not None
    matching_deny, matching_ask, matching_allow = _matching_rules_for_input(
        command, tool_permission_context, "prefix",
        skip_compound_check=skip_compound,
    )

    # 2a. Deny if command has a deny rule
    if matching_deny:
        return PermissionDenyDecision(
            message=f"Permission to use Bash with command {command} has been denied.",
            decision_reason={"type": "rule", "rule": matching_deny[0]},
        )

    # 2b. Ask if command has an ask rule
    if matching_ask:
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name()),
            decision_reason={"type": "rule", "rule": matching_ask[0]},
        )

    # 3. Check path constraints
    # Import here to avoid circular dependencies
    try:
        from optimus.tools.bash_tool.path_validation import check_path_constraints
        path_result = check_path_constraints(
            command,
            get_cwd(),
            tool_permission_context,
            compound_command_has_cd,
            getattr(ast_command, "redirects", None) if ast_command else None,
            [ast_command] if ast_command else None,
        )
        if path_result.behavior != "passthrough":
            return path_result
    except ImportError:
        pass  # path_validation not yet ported

    # 4. Allow if command had an exact match allow
    if exact_match_result.behavior == "allow":
        return exact_match_result

    # 5. Allow if command has an allow rule
    if matching_allow:
        return PermissionAllowDecision(
            updated_input={"command": command},
            decision_reason={"type": "rule", "rule": matching_allow[0]},
        )

    # 5b. Check sed constraints
    try:
        from optimus.tools.bash_tool.sed_validation import check_sed_constraints
        sed_result = check_sed_constraints(command, tool_permission_context)
        if sed_result.behavior != "passthrough":
            return sed_result
    except ImportError:
        pass  # sed_validation not yet ported

    # 6. Check for mode-specific permission handling
    try:
        from optimus.tools.bash_tool.mode_validation import check_permission_mode
        mode_result = check_permission_mode(command, tool_permission_context)
        if mode_result.behavior != "passthrough":
            return mode_result
    except ImportError:
        pass  # mode_validation not yet ported

    # 7. Check read-only rules
    try:
        from optimus.tools.bash_tool.bash_tool import BashTool
        if BashTool.is_read_only({"command": command}):
            return PermissionAllowDecision(
                updated_input={"command": command},
                decision_reason={"type": "other", "reason": "Read-only command is allowed"},
            )
    except (ImportError, AttributeError):
        pass

    # 8. Passthrough since no rules match, will trigger permission prompt
    decision_reason = {
        "type": "other",
        "reason": "This command requires approval",
    }
    return PermissionPassthroughDecision(
        message=create_permission_request_message(_tool_name(), decision_reason),
        decision_reason=decision_reason,
        suggestions=_suggestion_for_exact_command(command),
    )


# ---------------------------------------------------------------------------
# checkCommandAndSuggestRules
# ---------------------------------------------------------------------------

async def check_command_and_suggest_rules(
    command: str,
    tool_permission_context: ToolPermissionContext,
    command_prefix_result: Any | None = None,
    compound_command_has_cd: bool = False,
    ast_parse_succeeded: bool = False,
) -> PermissionResult:
    """
    Processes an individual subcommand and applies prefix checks & suggestions.

    Mirrors checkCommandAndSuggestRules() from bashPermissions.ts.
    """
    # 1. Check exact match first
    exact_match_result = bash_tool_check_exact_match_permission(
        command, tool_permission_context
    )
    if exact_match_result.behavior != "passthrough":
        return exact_match_result

    # 2. Check the command prefix
    permission_result = bash_tool_check_permission(
        command, tool_permission_context, compound_command_has_cd,
    )

    # 2a. Deny/ask if command was explicitly denied/asked
    if permission_result.behavior in ("deny", "ask"):
        return permission_result

    # 3. Ask for permission if command injection is detected.
    # Skip when the AST parse already succeeded — tree-sitter has verified
    # there are no hidden substitutions or structural tricks.
    if (
        not ast_parse_succeeded
        and not is_env_truthy(
            os.environ.get("CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK", "")
        )
    ):
        safety_result = await bash_command_is_safe_async(command)

        if safety_result.behavior != "passthrough":
            decision_reason: PermissionDecisionReason = {
                "type": "other",
                "reason": (
                    safety_result.message
                    if safety_result.behavior == "ask" and hasattr(safety_result, "message")
                    and safety_result.message
                    else "This command contains patterns that could pose security risks and requires approval"
                ),
            }
            return PermissionAskDecision(
                message=create_permission_request_message(_tool_name(), decision_reason),
                decision_reason=decision_reason,
                suggestions=[],  # Don't suggest saving a potentially dangerous command
            )

    # 4. Allow if command was allowed
    if permission_result.behavior == "allow":
        return permission_result

    # 5. Suggest prefix if available, otherwise exact command
    prefix_val = None
    if command_prefix_result is not None:
        if isinstance(command_prefix_result, dict):
            prefix_val = command_prefix_result.get("command_prefix")
        elif hasattr(command_prefix_result, "command_prefix"):
            prefix_val = command_prefix_result.command_prefix

    suggested_updates = (
        _suggestion_for_prefix(prefix_val)
        if prefix_val
        else _suggestion_for_exact_command(command)
    )

    return PermissionPassthroughDecision(
        message=getattr(permission_result, "message", create_permission_request_message(_tool_name())),
        decision_reason=getattr(permission_result, "decision_reason", None),
        suggestions=suggested_updates,
    )


# ---------------------------------------------------------------------------
# Sandbox auto-allow
# ---------------------------------------------------------------------------

def _check_sandbox_auto_allow(
    command: str,
    tool_permission_context: ToolPermissionContext,
) -> PermissionResult:
    """
    Checks if a command should be auto-allowed when sandboxed.
    Returns early if there are explicit deny/ask rules that should be respected.

    Mirrors checkSandboxAutoAllow() from bashPermissions.ts.
    """
    command = command.strip()

    # Check for explicit deny/ask rules on the full command (exact + prefix)
    matching_deny, matching_ask, _ = _matching_rules_for_input(
        command, tool_permission_context, "prefix"
    )

    # Return immediately if there's an explicit deny rule
    if matching_deny:
        return PermissionDenyDecision(
            message=f"Permission to use Bash with command {command} has been denied.",
            decision_reason={"type": "rule", "rule": matching_deny[0]},
        )

    # SECURITY: For compound commands, check each subcommand against deny/ask rules.
    subcommands = split_command(command)
    if len(subcommands) > 1:
        first_ask_rule: PermissionRule | None = None
        for sub in subcommands:
            sub_deny, sub_ask, _ = _matching_rules_for_input(
                sub, tool_permission_context, "prefix"
            )
            if sub_deny:
                return PermissionDenyDecision(
                    message=f"Permission to use Bash with command {command} has been denied.",
                    decision_reason={"type": "rule", "rule": sub_deny[0]},
                )
            if first_ask_rule is None and sub_ask:
                first_ask_rule = sub_ask[0]

        if first_ask_rule is not None:
            return PermissionAskDecision(
                message=create_permission_request_message(_tool_name()),
                decision_reason={"type": "rule", "rule": first_ask_rule},
            )

    # Full-command ask check (after all deny sources have been exhausted)
    if matching_ask:
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name()),
            decision_reason={"type": "rule", "rule": matching_ask[0]},
        )

    # No explicit rules, so auto-allow with sandbox
    return PermissionAllowDecision(
        updated_input={"command": command},
        decision_reason={
            "type": "other",
            "reason": "Auto-allowed with sandbox (autoAllowBashIfSandboxed enabled)",
        },
    )


# ---------------------------------------------------------------------------
# Helper: filter cd ${cwd} prefix subcommands
# ---------------------------------------------------------------------------

def _filter_cd_cwd_subcommands(
    raw_subcommands: list[str],
    ast_commands: list[Any] | None,
    cwd: str,
    cwd_mingw: str,
) -> tuple[list[str], list[Any | None]]:
    """
    Filter out `cd ${cwd}` prefix subcommands, keeping ast_commands aligned.
    Mirrors filterCdCwdSubcommands() from bashPermissions.ts.
    """
    subcommands: list[str] = []
    ast_commands_by_idx: list[Any | None] = []
    for i, cmd in enumerate(raw_subcommands):
        if cmd == f"cd {cwd}" or cmd == f"cd {cwd_mingw}":
            continue
        subcommands.append(cmd)
        ast_commands_by_idx.append(ast_commands[i] if ast_commands else None)
    return subcommands, ast_commands_by_idx


# ---------------------------------------------------------------------------
# Early-exit deny helpers
# ---------------------------------------------------------------------------

def _check_early_exit_deny(
    command: str,
    tool_permission_context: ToolPermissionContext,
) -> PermissionResult | None:
    """
    Returns the exact-match result if non-passthrough (deny/ask/allow),
    then checks prefix/wildcard deny rules. Returns None if neither matched.
    Mirrors checkEarlyExitDeny() from bashPermissions.ts.
    """
    exact_result = bash_tool_check_exact_match_permission(command, tool_permission_context)
    if exact_result.behavior != "passthrough":
        return exact_result

    matching_deny, _, _ = _matching_rules_for_input(command, tool_permission_context, "prefix")
    if matching_deny:
        return PermissionDenyDecision(
            message=f"Permission to use Bash with command {command} has been denied.",
            decision_reason={"type": "rule", "rule": matching_deny[0]},
        )
    return None


def _check_semantics_deny(
    command: str,
    tool_permission_context: ToolPermissionContext,
    commands: list[Any],
) -> PermissionResult | None:
    """
    Full-command and per-SimpleCommand deny enforcement for the AST checkSemantics path.
    Mirrors checkSemanticsDeny() from bashPermissions.ts.
    """
    full_cmd = _check_early_exit_deny(command, tool_permission_context)
    if full_cmd is not None:
        return full_cmd
    for cmd_node in commands:
        cmd_text = cmd_node.text if hasattr(cmd_node, "text") else str(cmd_node)
        sub_deny, _, _ = _matching_rules_for_input(
            cmd_text, tool_permission_context, "prefix"
        )
        if sub_deny:
            return PermissionDenyDecision(
                message=f"Permission to use Bash with command {command} has been denied.",
                decision_reason={"type": "rule", "rule": sub_deny[0]},
            )
    return None


# ---------------------------------------------------------------------------
# Classifier helpers
# ---------------------------------------------------------------------------

def _build_pending_classifier_check(
    command: str,
    tool_permission_context: ToolPermissionContext,
) -> PendingClassifierCheck | None:
    """
    Builds the pending classifier check metadata if classifier is enabled.
    Returns None if classifier is disabled or no allow descriptions exist.
    Mirrors buildPendingClassifierCheck() from bashPermissions.ts.
    """
    if not is_classifier_permissions_enabled():
        return None
    if tool_permission_context.mode == "bypassPermissions":
        return None

    allow_descriptions = get_bash_prompt_allow_descriptions(tool_permission_context)
    if not allow_descriptions:
        return None

    return PendingClassifierCheck(
        command=command,
        cwd=get_cwd(),
        descriptions=allow_descriptions,
    )


# Module-level dict of speculative classifier checks: command → asyncio.Task
_speculative_checks: dict[str, asyncio.Task[ClassifierResult]] = {}


def peek_speculative_classifier_check(command: str) -> asyncio.Task[ClassifierResult] | None:
    """Return the speculative classifier task for a command, if any."""
    return _speculative_checks.get(command)


def start_speculative_classifier_check(
    command: str,
    tool_permission_context: ToolPermissionContext,
    signal: Any,
    is_non_interactive_session: bool,
) -> bool:
    """
    Start a speculative bash allow classifier check early.
    Mirrors startSpeculativeClassifierCheck() from bashPermissions.ts.
    """
    if not is_classifier_permissions_enabled():
        return False
    if tool_permission_context.mode == "bypassPermissions":
        return False

    allow_descriptions = get_bash_prompt_allow_descriptions(tool_permission_context)
    if not allow_descriptions:
        return False

    cwd = get_cwd()

    async def _run() -> ClassifierResult:
        return await classify_bash_command(
            command, cwd, allow_descriptions, "allow",
            signal, is_non_interactive_session,
        )

    task = asyncio.ensure_future(_run())
    # Prevent unhandled rejection if aborted before consumed.
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    _speculative_checks[command] = task
    return True


def consume_speculative_classifier_check(command: str) -> asyncio.Task[ClassifierResult] | None:
    """
    Consume a speculative classifier check result for the given command.
    Returns the task if one exists (and removes it from the dict), or None.
    """
    task = _speculative_checks.pop(command, None)
    return task


def clear_speculative_checks() -> None:
    """Cancel and clear all speculative classifier checks."""
    for task in _speculative_checks.values():
        task.cancel()
    _speculative_checks.clear()


async def await_classifier_auto_approval(
    pending_check: PendingClassifierCheck,
    signal: Any,
    is_non_interactive_session: bool,
) -> PermissionDecisionReason | None:
    """
    Await a pending classifier check and return a PermissionDecisionReason if
    high-confidence allow, or None otherwise.

    Used by swarm agents to gate permission forwarding.
    Mirrors awaitClassifierAutoApproval() from bashPermissions.ts.
    """
    command = pending_check.command
    cwd = pending_check.cwd
    descriptions = pending_check.descriptions

    speculative = consume_speculative_classifier_check(command)
    if speculative is not None:
        classifier_result = await speculative
    else:
        classifier_result = await classify_bash_command(
            command, cwd, descriptions, "allow",
            signal, is_non_interactive_session,
        )

    if (
        classifier_result.matches
        and classifier_result.confidence == "high"
    ):
        return {
            "type": "classifier",
            "classifier": "bash_allow",
            "reason": f'Allowed by prompt rule: "{classifier_result.matched_description}"',
        }
    return None


async def execute_async_classifier_check(
    pending_check: PendingClassifierCheck,
    signal: Any,
    is_non_interactive_session: bool,
    should_continue: Callable[[], bool],
    on_allow: Callable[[PermissionDecisionReason], None],
    on_complete: Callable[[], None] | None = None,
) -> None:
    """
    Execute the bash allow classifier check asynchronously.
    This runs in the background while the permission prompt is shown.
    If the classifier allows with high confidence and the user hasn't interacted,
    auto-approves.

    Mirrors executeAsyncClassifierCheck() from bashPermissions.ts.
    """
    command = pending_check.command
    cwd = pending_check.cwd
    descriptions = pending_check.descriptions

    speculative = consume_speculative_classifier_check(command)
    try:
        if speculative is not None:
            classifier_result = await speculative
        else:
            classifier_result = await classify_bash_command(
                command, cwd, descriptions, "allow",
                signal, is_non_interactive_session,
            )
    except Exception as e:
        # When the coordinator session is cancelled, the abort signal fires and
        # the classifier API call rejects. This is expected.
        if on_complete:
            on_complete()
        # Re-raise non-abort errors
        if "Abort" not in type(e).__name__ and "Cancel" not in type(e).__name__:
            raise
        return

    if not should_continue():
        return

    if (
        classifier_result.matches
        and classifier_result.confidence == "high"
    ):
        on_allow({
            "type": "classifier",
            "classifier": "bash_allow",
            "reason": f'Allowed by prompt rule: "{classifier_result.matched_description}"',
        })
    else:
        if on_complete:
            on_complete()


# ---------------------------------------------------------------------------
# isNormalizedGitCommand / isNormalizedCdCommand / commandHasAnyCd
# ---------------------------------------------------------------------------

def is_normalized_git_command(command: str) -> bool:
    """
    Checks if a subcommand is a git command after normalizing away safe wrappers.

    SECURITY: Must normalize before matching to prevent bypasses like:
      'git' status    — shell quotes hide the command
      NO_COLOR=1 git status — env var prefix hides the command
    """
    # Fast path: catch the most common case before any parsing
    if command.startswith("git ") or command == "git":
        return True
    stripped = strip_safe_wrappers(command)
    parsed = try_parse_shell_command(stripped)
    if parsed.success and parsed.tokens:
        tokens = parsed.tokens
        if tokens[0] == "git":
            return True
        # "xargs git ..." — xargs runs git in the current directory.
        if tokens[0] == "xargs" and "git" in tokens:
            return True
        return False
    return bool(re.match(r"^git(?:\s|$)", stripped))


def is_normalized_cd_command(command: str) -> bool:
    """
    Checks if a subcommand is a cd command after normalizing away safe wrappers.
    Also matches pushd/popd — they change cwd just like cd.

    SECURITY: Must normalize before matching.
    Mirrors isNormalizedCdCommand() from bashPermissions.ts.
    """
    stripped = strip_safe_wrappers(command)
    parsed = try_parse_shell_command(stripped)
    if parsed.success and parsed.tokens:
        cmd = parsed.tokens[0]
        return cmd in ("cd", "pushd", "popd")
    return bool(re.match(r"^(?:cd|pushd|popd)(?:\s|$)", stripped))


def command_has_any_cd(command: str) -> bool:
    """
    Checks if a compound command contains any cd command,
    using normalized detection that handles env var prefixes and shell quotes.
    Mirrors commandHasAnyCd() from bashPermissions.ts.
    """
    return any(
        is_normalized_cd_command(subcmd.strip())
        for subcmd in split_command(command)
    )


# ---------------------------------------------------------------------------
# bashToolHasPermission — main async entry point
# ---------------------------------------------------------------------------

async def bash_tool_has_permission(
    command: str,
    context: ToolUseContext,
    get_command_subcommand_prefix_fn: Any = None,
) -> PermissionResult:
    """
    The main implementation to check if we need to ask for user permission
    to call BashTool with a given command.

    Mirrors bashToolHasPermission() from bashPermissions.ts (lines 1663-2557).

    Decision flow:
    0. AST-based security parse (tree-sitter, if available).
    1. If too-complex → early deny/ask.
    2. If simple AST → check semantics.
    3. Legacy shell-quote pre-check (when tree-sitter unavailable).
    4. Sandbox auto-allow (if enabled).
    5. Exact-match deny.
    6. Classifier deny/ask (if enabled).
    7. Command operator permissions (pipes, etc.).
    8. Legacy misparsing gate (if AST unavailable).
    9. Split into subcommands.
    10. Cap subcommand fanout.
    11. Multiple-cd check.
    12. cd+git security check.
    13. Per-subcommand permission checks.
    14. Output redirection validation.
    15. Command injection check (per subcommand).
    16. Suggest rules and return.
    """
    app_state = context.get_app_state() if hasattr(context, "get_app_state") else None
    tool_permission_context = (
        app_state.tool_permission_context
        if app_state and hasattr(app_state, "tool_permission_context")
        else getattr(context, "tool_permission_context", None)
    )

    injection_check_disabled = is_env_truthy(
        os.environ.get("CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK", "")
    )

    # 0. AST-based security parse (tree-sitter)
    ast_root = None
    ast_result: dict = {"kind": "parse-unavailable"}
    ast_subcommands: list[str] | None = None
    ast_redirects: list[Any] | None = None
    ast_commands: list[Any] | None = None

    if not injection_check_disabled:
        try:
            from optimus.utils.bash.bash_parser import parse_command_raw
            ast_root = await parse_command_raw(command)
            if ast_root is not None:
                try:
                    from optimus.utils.bash.ast import parse_for_security_from_ast, check_semantics
                    ast_result = parse_for_security_from_ast(command, ast_root)
                except ImportError:
                    ast_result = {"kind": "parse-unavailable"}
        except (ImportError, Exception):
            ast_result = {"kind": "parse-unavailable"}

    # 1. too-complex → ask (but respect deny rules)
    if ast_result.get("kind") == "too-complex":
        early_exit = _check_early_exit_deny(command, tool_permission_context)
        if early_exit is not None:
            return early_exit
        decision_reason: PermissionDecisionReason = {
            "type": "other",
            "reason": ast_result.get("reason", "Command is too complex to analyze"),
        }
        result: PermissionResult = PermissionAskDecision(
            message=create_permission_request_message(_tool_name(), decision_reason),
            decision_reason=decision_reason,
            suggestions=[],
            pending_classifier_check=_build_pending_classifier_check(
                command, tool_permission_context
            ),
        )
        return result

    # 2. simple AST → check semantics
    if ast_result.get("kind") == "simple":
        ast_cmds = ast_result.get("commands", [])
        try:
            from optimus.utils.bash.ast import check_semantics
            sem = check_semantics(ast_cmds)
        except ImportError:
            sem = {"ok": True}

        if not sem.get("ok", True):
            early_exit = _check_semantics_deny(command, tool_permission_context, ast_cmds)
            if early_exit is not None:
                return early_exit
            decision_reason = {
                "type": "other",
                "reason": sem.get("reason", "Command semantics check failed"),
            }
            return PermissionAskDecision(
                message=create_permission_request_message(_tool_name(), decision_reason),
                decision_reason=decision_reason,
                suggestions=[],
            )

        # Stash tokenized subcommands for use below.
        ast_subcommands = [c.text if hasattr(c, "text") else str(c) for c in ast_cmds]
        ast_redirects = [r for c in ast_cmds for r in (getattr(c, "redirects", []) or [])]
        ast_commands = list(ast_cmds)

    # 3. Legacy shell-quote pre-check (when tree-sitter unavailable)
    if ast_result.get("kind") == "parse-unavailable":
        parse_result = try_parse_shell_command(command)
        if not parse_result.success:
            decision_reason = {
                "type": "other",
                "reason": f"Command contains malformed syntax that cannot be parsed: {parse_result.error}",
            }
            return PermissionAskDecision(
                message=create_permission_request_message(_tool_name(), decision_reason),
                decision_reason=decision_reason,
            )

    # 4. Check sandbox auto-allow
    try:
        from optimus.utils.sandbox.sandbox_adapter import SandboxManager
        from optimus.tools.bash_tool.should_use_sandbox import should_use_sandbox
        if (
            SandboxManager.is_sandboxing_enabled()
            and SandboxManager.is_auto_allow_bash_if_sandboxed_enabled()
            and should_use_sandbox(command)
        ):
            sandbox_result = _check_sandbox_auto_allow(command, tool_permission_context)
            if sandbox_result.behavior != "passthrough":
                return sandbox_result
    except ImportError:
        pass

    # Check exact match first
    exact_match_result = bash_tool_check_exact_match_permission(
        command, tool_permission_context
    )

    # Exact command was denied
    if exact_match_result.behavior == "deny":
        return exact_match_result

    # 5b. Check Bash prompt deny and ask rules in parallel (classifier)
    if is_classifier_permissions_enabled():
        deny_descriptions = get_bash_prompt_deny_descriptions(tool_permission_context)
        ask_descriptions = get_bash_prompt_ask_descriptions(tool_permission_context)
        has_deny = bool(deny_descriptions)
        has_ask = bool(ask_descriptions)

        if has_deny or has_ask:
            abort_signal = getattr(
                getattr(context, "abort_controller", None), "signal", None
            )
            is_non_interactive = getattr(
                getattr(context, "options", None), "is_non_interactive_session", False
            )

            deny_task = (
                asyncio.ensure_future(
                    classify_bash_command(
                        command, get_cwd(), deny_descriptions, "deny",
                        abort_signal, is_non_interactive,
                    )
                ) if has_deny else None
            )
            ask_task = (
                asyncio.ensure_future(
                    classify_bash_command(
                        command, get_cwd(), ask_descriptions, "ask",
                        abort_signal, is_non_interactive,
                    )
                ) if has_ask else None
            )

            deny_result: ClassifierResult | None = None
            ask_result: ClassifierResult | None = None

            if deny_task:
                deny_result = await deny_task
            if ask_task:
                ask_result = await ask_task

            # Deny takes precedence
            if deny_result and deny_result.matches and deny_result.confidence == "high":
                return PermissionDenyDecision(
                    message=f'Denied by Bash prompt rule: "{deny_result.matched_description}"',
                    decision_reason={
                        "type": "other",
                        "reason": f'Denied by Bash prompt rule: "{deny_result.matched_description}"',
                    },
                )

            if ask_result and ask_result.matches and ask_result.confidence == "high":
                suggestions = _suggestion_for_exact_command(command)
                return PermissionAskDecision(
                    message=create_permission_request_message(_tool_name()),
                    decision_reason={
                        "type": "other",
                        "reason": f'Required by Bash prompt rule: "{ask_result.matched_description}"',
                    },
                    suggestions=suggestions,
                    pending_classifier_check=_build_pending_classifier_check(
                        command, tool_permission_context
                    ),
                )

    # 6. Check for non-subcommand Bash operators like `>`, `|`, etc.
    try:
        from optimus.tools.bash_tool.bash_command_helpers import check_command_operator_permissions
        command_operator_result = await check_command_operator_permissions(
            command,
            lambda c: bash_tool_has_permission(c, context, get_command_subcommand_prefix_fn),
            {
                "is_normalized_cd_command": is_normalized_cd_command,
                "is_normalized_git_command": is_normalized_git_command,
            },
            ast_root,
        )
        if command_operator_result.behavior != "passthrough":
            if command_operator_result.behavior == "allow":
                # SECURITY: must still validate original command
                safety_result = (
                    await bash_command_is_safe_async(command)
                    if ast_subcommands is None
                    else None
                )
                if (
                    safety_result is not None
                    and safety_result.behavior not in ("passthrough", "allow")
                ):
                    if app_state and hasattr(context, "get_app_state"):
                        app_state = context.get_app_state()
                    return PermissionAskDecision(
                        message=create_permission_request_message(_tool_name(), {
                            "type": "other",
                            "reason": getattr(safety_result, "message", None)
                                      or "Command contains patterns that require approval",
                        }),
                        decision_reason={
                            "type": "other",
                            "reason": getattr(safety_result, "message", None)
                                      or "Command contains patterns that require approval",
                        },
                        pending_classifier_check=_build_pending_classifier_check(
                            command, tool_permission_context
                        ),
                    )

                if app_state and hasattr(context, "get_app_state"):
                    app_state = context.get_app_state()
                # Check path constraints on original command
                try:
                    from optimus.tools.bash_tool.path_validation import check_path_constraints
                    path_result = check_path_constraints(
                        command, get_cwd(), tool_permission_context,
                        command_has_any_cd(command),
                        ast_redirects, ast_commands,
                    )
                    if path_result.behavior != "passthrough":
                        return path_result
                except ImportError:
                    pass

            if command_operator_result.behavior == "ask":
                if app_state and hasattr(context, "get_app_state"):
                    app_state = context.get_app_state()
                return PermissionAskDecision(
                    message=getattr(command_operator_result, "message", create_permission_request_message(_tool_name())),
                    decision_reason=getattr(command_operator_result, "decision_reason", None),
                    suggestions=getattr(command_operator_result, "suggestions", None),
                    pending_classifier_check=_build_pending_classifier_check(
                        command, tool_permission_context
                    ),
                )

            return command_operator_result
    except ImportError:
        pass

    # 7. Legacy misparsing gate (when tree-sitter unavailable).
    if (
        ast_subcommands is None
        and not injection_check_disabled
    ):
        original_safety_result = await bash_command_is_safe_async(command)
        is_misparsing = (
            original_safety_result.behavior == "ask"
            and getattr(original_safety_result, "is_bash_security_check_for_misparsing", False)
        )
        if is_misparsing:
            remainder = strip_safe_heredoc_substitutions(command)
            remainder_result = (
                await bash_command_is_safe_async(remainder)
                if remainder is not None
                else None
            )
            if remainder is None or (
                remainder_result is not None
                and remainder_result.behavior == "ask"
                and getattr(remainder_result, "is_bash_security_check_for_misparsing", False)
            ):
                if app_state and hasattr(context, "get_app_state"):
                    app_state = context.get_app_state()
                exact_result = bash_tool_check_exact_match_permission(
                    command, tool_permission_context
                )
                if exact_result.behavior == "allow":
                    return exact_result
                decision_reason = {
                    "type": "other",
                    "reason": getattr(original_safety_result, "message", None)
                              or "Command requires approval",
                }
                return PermissionAskDecision(
                    message=create_permission_request_message(_tool_name(), decision_reason),
                    decision_reason=decision_reason,
                    suggestions=[],
                    pending_classifier_check=_build_pending_classifier_check(
                        command, tool_permission_context
                    ),
                )

    # 8. Split into subcommands
    cwd = get_cwd()
    # On Windows, convert backslashes to forward slashes for cd-cwd matching
    try:
        from optimus.utils.platform import get_platform
        from optimus.utils.windows_paths import windows_path_to_posix_path
        cwd_mingw = windows_path_to_posix_path(cwd) if get_platform() == "windows" else cwd
    except ImportError:
        cwd_mingw = cwd

    raw_subcommands = ast_subcommands if ast_subcommands is not None else split_command(command)
    subcommands, ast_commands_by_idx = _filter_cd_cwd_subcommands(
        raw_subcommands, ast_commands, cwd, cwd_mingw
    )

    # 9. CC-643: Cap subcommand fanout (legacy path only)
    if ast_subcommands is None and len(subcommands) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
        decision_reason = {
            "type": "other",
            "reason": f"Command splits into {len(subcommands)} subcommands, too many to safety-check individually",
        }
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name(), decision_reason),
            decision_reason=decision_reason,
        )

    # 10. Ask if there are multiple `cd` commands
    cd_commands = [sub for sub in subcommands if is_normalized_cd_command(sub)]
    if len(cd_commands) > 1:
        decision_reason = {
            "type": "other",
            "reason": "Multiple directory changes in one command require approval for clarity",
        }
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name(), decision_reason),
            decision_reason=decision_reason,
        )

    compound_command_has_cd = len(cd_commands) > 0

    # 11. SECURITY: Block compound commands that have both cd AND git.
    # Prevents sandbox escape via: cd /malicious/dir && git status
    if compound_command_has_cd:
        has_git_command = any(is_normalized_git_command(cmd.strip()) for cmd in subcommands)
        if has_git_command:
            decision_reason = {
                "type": "other",
                "reason": "Compound commands with cd and git require approval to prevent bare repository attacks",
            }
            return PermissionAskDecision(
                message=create_permission_request_message(_tool_name(), decision_reason),
                decision_reason=decision_reason,
            )

    if app_state and hasattr(context, "get_app_state"):
        app_state = context.get_app_state()
    # Re-fetch tool_permission_context in case user hit shift+tab
    if app_state and hasattr(app_state, "tool_permission_context"):
        tool_permission_context = app_state.tool_permission_context

    # 12. Per-subcommand permission decisions (synchronous rule checks)
    subcommand_permission_decisions = [
        bash_tool_check_permission(
            cmd, tool_permission_context,
            compound_command_has_cd,
            ast_commands_by_idx[i],
        )
        for i, cmd in enumerate(subcommands)
    ]

    # Deny if any subcommands are denied
    denied_sub = next(
        (r for r in subcommand_permission_decisions if r.behavior == "deny"), None
    )
    if denied_sub is not None:
        return PermissionDenyDecision(
            message=f"Permission to use Bash with command {command} has been denied.",
            decision_reason={
                "type": "subcommandResults",
                "reasons": dict(zip(subcommands, subcommand_permission_decisions)),
            },
        )

    # 13. Validate output redirections on the ORIGINAL command
    try:
        from optimus.tools.bash_tool.path_validation import check_path_constraints
        path_result = check_path_constraints(
            command, get_cwd(), tool_permission_context,
            compound_command_has_cd,
            ast_redirects, ast_commands,
        )
        if path_result.behavior == "deny":
            return path_result
    except ImportError:
        path_result = PermissionPassthroughDecision(
            message="",
            decision_reason=None,
        )

    ask_sub = next(
        (r for r in subcommand_permission_decisions if r.behavior == "ask"), None
    )
    non_allow_count = sum(
        1 for r in subcommand_permission_decisions if r.behavior != "allow"
    )

    # SECURITY (GH#28784): Only short-circuit on path-constraint ask when no
    # subcommand independently produced an ask.
    if path_result.behavior == "ask" and ask_sub is None:
        return path_result

    if ask_sub is not None and non_allow_count == 1:
        if app_state and hasattr(context, "get_app_state"):
            app_state = context.get_app_state()
        if app_state and hasattr(app_state, "tool_permission_context"):
            tool_permission_context = app_state.tool_permission_context
        return PermissionAskDecision(
            message=getattr(ask_sub, "message", create_permission_request_message(_tool_name())),
            decision_reason=getattr(ask_sub, "decision_reason", None),
            suggestions=getattr(ask_sub, "suggestions", None),
            pending_classifier_check=_build_pending_classifier_check(
                command, tool_permission_context
            ),
        )

    # Allow if exact command was allowed
    if exact_match_result.behavior == "allow":
        return exact_match_result

    # 14. Per-subcommand command injection check (legacy path only)
    has_possible_injection = False
    if ast_subcommands is None and not injection_check_disabled:
        results = await asyncio.gather(
            *[bash_command_is_safe_async(c) for c in subcommands]
        )
        has_possible_injection = any(r.behavior != "passthrough" for r in results)

    if (
        all(r.behavior == "allow" for r in subcommand_permission_decisions)
        and not has_possible_injection
    ):
        return PermissionAllowDecision(
            updated_input={"command": command},
            decision_reason={
                "type": "subcommandResults",
                "reasons": dict(zip(subcommands, subcommand_permission_decisions)),
            },
        )

    # 15. Query command prefix (only when custom fn injected, e.g., in tests)
    command_subcommand_prefix = None
    if get_command_subcommand_prefix_fn is not None:
        abort_signal = getattr(
            getattr(context, "abort_controller", None), "signal", None
        )
        is_non_interactive = getattr(
            getattr(context, "options", None), "is_non_interactive_session", False
        )
        command_subcommand_prefix = await get_command_subcommand_prefix_fn(
            command, abort_signal, is_non_interactive,
        )

    # If there is only one command, no need to process subcommands
    if app_state and hasattr(context, "get_app_state"):
        app_state = context.get_app_state()
    if app_state and hasattr(app_state, "tool_permission_context"):
        tool_permission_context = app_state.tool_permission_context

    if len(subcommands) == 1:
        result = await check_command_and_suggest_rules(
            subcommands[0],
            tool_permission_context,
            command_subcommand_prefix,
            compound_command_has_cd,
            ast_subcommands is not None,
        )
        if result.behavior in ("ask", "passthrough"):
            if app_state and hasattr(context, "get_app_state"):
                app_state = context.get_app_state()
            if app_state and hasattr(app_state, "tool_permission_context"):
                tool_permission_context = app_state.tool_permission_context
            return PermissionAskDecision(
                message=getattr(result, "message", create_permission_request_message(_tool_name())),
                decision_reason=getattr(result, "decision_reason", None),
                suggestions=getattr(result, "suggestions", None),
                pending_classifier_check=_build_pending_classifier_check(
                    command, tool_permission_context
                ),
            )
        return result

    # 16. Check subcommand permission results (full async path)
    subcommand_results: dict[str, PermissionResult] = {}
    for i, subcommand in enumerate(subcommands):
        sub_prefix = None
        if command_subcommand_prefix and hasattr(command_subcommand_prefix, "subcommand_prefixes"):
            sub_prefix = command_subcommand_prefix.subcommand_prefixes.get(subcommand)

        subcommand_results[subcommand] = await check_command_and_suggest_rules(
            subcommand,
            tool_permission_context,
            sub_prefix,
            compound_command_has_cd,
            ast_subcommands is not None,
        )

    # Allow if all subcommands are allowed
    if all(r.behavior == "allow" for r in subcommand_results.values()):
        return PermissionAllowDecision(
            updated_input={"command": command},
            decision_reason={
                "type": "subcommandResults",
                "reasons": subcommand_results,
            },
        )

    # Otherwise, ask for permission — collect suggested rules
    collected_rules: dict[str, PermissionRuleValue] = {}
    for subcommand, perm_result in subcommand_results.items():
        if perm_result.behavior in ("ask", "passthrough"):
            updates = getattr(perm_result, "suggestions", None)
            rules = extract_rules(updates)
            for rule in rules:
                rule_key = permission_rule_value_to_string(rule)
                collected_rules[rule_key] = rule

            # GH#28784: Synthesize a Bash(exact) rule for security-check asks
            # that carry no suggestions (so the UI shows the chained command).
            if (
                perm_result.behavior == "ask"
                and not rules
                and (
                    not hasattr(perm_result, "decision_reason")
                    or not perm_result.decision_reason
                    or perm_result.decision_reason.get("type") != "rule"
                )
            ):
                for rule in extract_rules(_suggestion_for_exact_command(subcommand)):
                    rule_key = permission_rule_value_to_string(rule)
                    collected_rules[rule_key] = rule

    decision_reason = {
        "type": "subcommandResults",
        "reasons": subcommand_results,
    }

    # GH#11380: Cap at MAX_SUGGESTED_RULES_FOR_COMPOUND
    capped_rules = list(collected_rules.values())[:MAX_SUGGESTED_RULES_FOR_COMPOUND]
    suggested_updates: list[PermissionUpdate] | None = (
        [{"type": "addRules", "rules": capped_rules, "behavior": "allow", "destination": "localSettings"}]
        if capped_rules
        else None
    )

    has_any_ask = ask_sub is not None or any(
        r.behavior == "ask" for r in subcommand_results.values()
    )

    if app_state and hasattr(context, "get_app_state"):
        app_state = context.get_app_state()
    if app_state and hasattr(app_state, "tool_permission_context"):
        tool_permission_context = app_state.tool_permission_context

    behavior = "ask" if has_any_ask else "passthrough"
    if behavior == "ask":
        return PermissionAskDecision(
            message=create_permission_request_message(_tool_name(), decision_reason),
            decision_reason=decision_reason,
            suggestions=suggested_updates,
            pending_classifier_check=_build_pending_classifier_check(
                command, tool_permission_context
            ),
        )
    else:
        return PermissionPassthroughDecision(
            message=create_permission_request_message(_tool_name(), decision_reason),
            decision_reason=decision_reason,
            suggestions=suggested_updates,
            pending_classifier_check=_build_pending_classifier_check(
                command, tool_permission_context
            ),
        )
