"""
ShellProvider Protocol and ShellResult dataclass.

Python port of src/utils/shell/shellProvider.ts

Defines the interface that every shell backend must implement.
Currently two concrete backends exist:
  - BashProvider  (optimus/utils/shell/bash_provider.py)
  - PowerShellProvider  (future — Windows only)

TypeScript uses a structural type; Python uses typing.Protocol for the same
effect, plus a dataclass for the execution result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Shell types
# ---------------------------------------------------------------------------

ShellType = Literal["bash", "powershell"]

SHELL_TYPES: tuple[ShellType, ...] = ("bash", "powershell")
DEFAULT_HOOK_SHELL: ShellType = "bash"

# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


@dataclass
class ShellResult:
    """
    Result of a shell command execution.

    Attributes:
        stdout:      Combined or separate stdout captured from the process.
        stderr:      Stderr captured from the process.
        exit_code:   Process exit code (None if the process was killed/timed out).
        timed_out:   True if the command exceeded its timeout.
        interrupted: True if the command was cancelled via abort signal.
        cwd:         Working directory after the command ran (read from temp file).
        output_file_path:  Path to the temp file that may hold full stdout if truncated.
        output_file_size:  Byte size of the output file (if written).
        duration_ms: Wall-clock milliseconds the command took.
    """

    stdout: str
    stderr: str
    exit_code: int | None = None
    timed_out: bool = False
    interrupted: bool = False
    cwd: str | None = None
    output_file_path: str | None = None
    output_file_size: int | None = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# ShellProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ShellProvider(Protocol):
    """
    Interface that every shell execution backend must satisfy.

    Mirrors the ShellProvider type from shellProvider.ts.

    Attributes:
        type:      Which shell type this provider wraps ('bash' or 'powershell').
        shell_path: Absolute path to the shell executable.
        detached:  Whether to spawn the subprocess in a detached process group.

    Methods:
        build_exec_command(command, id, sandbox_tmp_dir, use_sandbox)
            Build the full command string including all shell-specific setup
            (snapshot sourcing, extglob disabling, eval-wrapping, cwd tracking).
            Returns (command_string, cwd_file_path).

        get_spawn_args(command_string)
            Return the argv list for subprocess.create_subprocess_exec:
            e.g. ['-c', command_string] for bash.

        get_environment_overrides(command)
            Return extra env vars to merge before spawning.
    """

    type: ShellType
    shell_path: str
    detached: bool

    async def build_exec_command(
        self,
        command: str,
        id_: int | str,
        sandbox_tmp_dir: str | None,
        use_sandbox: bool,
    ) -> tuple[str, str]:
        """
        Build the command string and return (command_string, cwd_file_path).

        *cwd_file_path* is the path to the temp file that the shell writes its
        working directory to after the command completes.
        """
        ...

    def get_spawn_args(self, command_string: str) -> list[str]:
        """Return argv to pass after the shell executable."""
        ...

    async def get_environment_overrides(
        self, command: str
    ) -> dict[str, str]:
        """Return extra environment variables to set before spawning."""
        ...
