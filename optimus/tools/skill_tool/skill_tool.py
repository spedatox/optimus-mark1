"""SkillTool — execute a registered slash-command skill with optional arguments."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

SKILL_TOOL_NAME = "Skill"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skill": {
            "type": "string",
            "description": 'The skill name (e.g., "commit", "review-pr").',
        },
        "args": {
            "type": "string",
            "description": "Optional arguments for the skill.",
        },
    },
    "required": ["skill"],
}

DESCRIPTION = """\
Execute a registered skill (slash command) by name with optional arguments.
Skills are predefined prompts or macros loaded from .claude/commands/.
"""


class SkillTool(Tool):
    name: str = SKILL_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.commands import find_command, get_commands

        skill_name: str = input_data["skill"]
        args: str = input_data.get("args") or ""

        # Strip leading slash if provided
        if skill_name.startswith("/"):
            skill_name = skill_name[1:]

        commands = get_commands()
        command = find_command(skill_name, commands)
        if command is None:
            available = [c.name for c in commands]
            return [{"type": "text", "text": (
                f"Skill '{skill_name}' not found. Available: {', '.join(available)}"
            )}]

        # Expand the skill prompt, substituting $ARGS
        prompt = command.prompt_template
        if "$ARGS" in prompt:
            prompt = prompt.replace("$ARGS", args)
        elif args:
            prompt = f"{prompt}\n\n{args}"

        result = {
            "skill": skill_name,
            "prompt": prompt,
            "args": args,
        }
        return [{"type": "text", "text": json.dumps(result)}]


skill_tool = SkillTool()
