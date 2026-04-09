"""Commands package — slash command registry."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptCommand:
    name: str
    prompt_template: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)


_commands: list[PromptCommand] = []


def register_command(cmd: PromptCommand) -> None:
    _commands.append(cmd)


def get_commands() -> list[PromptCommand]:
    return list(_commands)


def find_command(name: str, commands: list[PromptCommand] | None = None) -> PromptCommand | None:
    cmds = commands if commands is not None else _commands
    for cmd in cmds:
        if cmd.name == name or name in cmd.aliases:
            return cmd
    return None
