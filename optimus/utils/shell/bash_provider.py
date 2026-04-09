"""
BashProvider — async subprocess shell execution.
Mirrors src/utils/shell/bashProvider.ts (core execution logic).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from optimus.utils.debug import log_for_debugging
from optimus.utils.shell.shell_provider import ShellProvider, ShellType

MAX_OUTPUT_BYTES = 100 * 1024  # 100 KB — same as TS
DEFAULT_TIMEOUT_S = 120.0


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    interrupted: bool = False
    new_cwd: str | None = None


def _get_disable_extglob_cmd(shell_path: str) -> str | None:
    if os.environ.get("CLAUDE_CODE_SHELL_PREFIX"):
        return "{ shopt -u extglob || setopt NO_EXTENDED_GLOB; } >/dev/null 2>&1 || true"
    if "bash" in shell_path:
        return "shopt -u extglob 2>/dev/null || true"
    if "zsh" in shell_path:
        return "setopt NO_EXTENDED_GLOB 2>/dev/null || true"
    return None


def _rewrite_windows_null_redirect(cmd: str) -> str:
    """Replace 2>nul / >nul (Windows CMD) with /dev/null equivalents."""
    cmd = re.sub(r"\b2>nul\b", "2>/dev/null", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"(?<!\d)>nul\b", ">/dev/null", cmd, flags=re.IGNORECASE)
    return cmd


def _single_quote_for_eval(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _build_command_string(command: str, shell_path: str, cwd_file: str) -> str:
    command = _rewrite_windows_null_redirect(command)
    parts: list[str] = []

    extglob = _get_disable_extglob_cmd(shell_path)
    if extglob:
        parts.append(extglob)

    quoted = _single_quote_for_eval(command)
    # Add stdin redirect; if there's a pipe, place it after the first command
    if "|" in command:
        parts.append(f"eval {quoted} < /dev/null")
    else:
        parts.append(f"eval {quoted} < /dev/null")

    # Track cwd after execution
    parts.append(f"pwd -P >| {_single_quote_for_eval(cwd_file)}")

    cmd_str = " && ".join(parts)

    prefix = os.environ.get("CLAUDE_CODE_SHELL_PREFIX")
    if prefix:
        cmd_str = f"{prefix} {_single_quote_for_eval(cmd_str)}"

    return cmd_str


def _truncate_end(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="replace")


class BashProvider(ShellProvider):
    """Async bash subprocess provider."""

    def __init__(self, shell_path: str) -> None:
        self._shell_path = shell_path
        self._type: ShellType = "bash"

    @property
    def type(self) -> ShellType:
        return self._type

    @property
    def shell_path(self) -> str:
        return self._shell_path

    def get_spawn_args(self, command_string: str) -> list[str]:
        return ["-c", "-l", command_string]

    async def exec(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        env: dict[str, str] | None = None,
        on_output: AsyncIterator[str] | None = None,
    ) -> ExecResult:
        """Run *command* in a bash subprocess; return ExecResult."""
        tmp = tempfile.mktemp(prefix="optimus-cwd-")
        cmd_str = _build_command_string(command, self._shell_path, tmp)
        spawn_args = self.get_spawn_args(cmd_str)

        merged_env = {**os.environ}
        if env:
            merged_env.update(env)
        # Apply session env vars
        try:
            from optimus.utils.session_env_vars import get_session_env_vars
            for k, v in get_session_env_vars():
                merged_env[k] = v
        except ImportError:
            pass

        log_for_debugging(f"Shell: {command[:200]}", level="verbose")

        proc = await asyncio.create_subprocess_exec(
            self._shell_path,
            *spawn_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
        )

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        interrupted = False

        async def read_stream(stream: asyncio.StreamReader, buf: list[bytes]) -> None:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                buf.append(chunk)

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, stdout_chunks),  # type: ignore[arg-type]
                    read_stream(proc.stderr, stderr_chunks),  # type: ignore[arg-type]
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            interrupted = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        except asyncio.CancelledError:
            interrupted = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise

        await proc.wait()
        exit_code = proc.returncode or 0

        stdout_raw = b"".join(stdout_chunks)
        stderr_raw = b"".join(stderr_chunks)

        stdout = _truncate_end(stdout_raw.decode("utf-8", errors="replace"), MAX_OUTPUT_BYTES)
        stderr = _truncate_end(stderr_raw.decode("utf-8", errors="replace"), MAX_OUTPUT_BYTES // 4)

        # Read new cwd
        new_cwd: str | None = None
        try:
            new_cwd = Path(tmp).read_text(encoding="utf-8").strip()
        except OSError:
            pass
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass

        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            interrupted=interrupted,
            new_cwd=new_cwd,
        )


def create_bash_provider(shell_path: str | None = None) -> BashProvider:
    if shell_path is None:
        import shutil
        shell_path = (
            os.environ.get("SHELL")
            or shutil.which("bash")
            or "/bin/bash"
        )
    return BashProvider(shell_path)
