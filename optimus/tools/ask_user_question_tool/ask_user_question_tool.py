"""AskUserQuestionTool — ask the user a question and wait for response."""
from __future__ import annotations
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

ASK_USER_QUESTION_TOOL_NAME = "AskFollowupQuestion"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The question to ask the user."},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["label"],
            },
            "description": "Optional list of answer options to present to the user.",
        },
        "multi_select": {"type": "boolean", "description": "Allow selecting multiple options."},
    },
    "required": ["question"],
}

DESCRIPTION = """\
Ask the user a clarifying question and wait for their response.
Use this when you need more information to proceed with a task.
Provide options when there are a fixed set of reasonable choices.
"""


class AskUserQuestionTool(Tool):
    name: str = ASK_USER_QUESTION_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        question: str = input_data["question"]
        options: list[dict] = input_data.get("options") or []

        # In non-interactive mode return a prompt to be surfaced by the caller.
        # In interactive REPL mode, the UI layer handles input collection.
        # We emit a special marker the REPL can detect.
        if options:
            opts_text = "\n".join(f"  {i+1}. {o['label']}" for i, o in enumerate(options))
            return [{"type": "text", "text": f"[QUESTION] {question}\n{opts_text}"}]
        return [{"type": "text", "text": f"[QUESTION] {question}"}]


ask_user_question_tool = AskUserQuestionTool()
