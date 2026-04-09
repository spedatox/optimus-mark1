"""
Shell prefix detection and formatting.

Python port of src/utils/bash/shellPrefix.ts

The sole public function `format_shell_prefix_command` builds a properly-
quoted command string when CLAUDE_CODE_SHELL_PREFIX is set — i.e. when the
user wants every shell command to be wrapped by a custom executable (e.g. a
sandbox wrapper or a remote-execution shim).
"""
from __future__ import annotations

from optimus.utils.bash.shell_quote import quote


def format_shell_prefix_command(prefix: str, command: str) -> str:
    """
    Format a command with a shell prefix wrapper.

    Parses *prefix* into an executable path plus optional arguments, then
    quotes both the executable and the *command* payload appropriately.

    Examples (from TS source):
        "bash"                      -> 'bash' 'command'
        "/usr/bin/bash -c"          -> '/usr/bin/bash' -c 'command'
        "C:\\Program Files\\...exe -c" -> 'C:\\Program Files\\...exe' -c 'command'

    Mirrors formatShellPrefixCommand() from shellPrefix.ts.

    The split point is the *last* occurrence of ' -' (space + dash), which
    separates the executable path from any trailing flag arguments.
    """
    space_before_dash = prefix.rfind(" -")
    if space_before_dash > 0:
        exec_path = prefix[:space_before_dash]
        args = prefix[space_before_dash + 1:]
        return f"{quote([exec_path])} {args} {quote([command])}"
    else:
        return f"{quote([prefix])} {quote([command])}"
