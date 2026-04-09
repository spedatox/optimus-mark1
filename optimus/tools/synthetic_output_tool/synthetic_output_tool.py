"""SyntheticOutputTool (StructuredOutput) — return final response as structured JSON."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

SYNTHETIC_OUTPUT_TOOL_NAME = "StructuredOutput"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Structured output — any JSON object matching the requested schema.",
    "additionalProperties": True,
}

DESCRIPTION = "Return structured output in the requested format."

PROMPT = """\
Use this tool to return your final response in the requested structured format.
You MUST call this tool exactly once at the end of your response to provide the structured output.
"""


class SyntheticOutputTool(Tool):
    name: str = SYNTHETIC_OUTPUT_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        # Validate against optional output_schema in ctx if provided
        output_schema: dict | None = getattr(ctx, "output_schema", None)
        if output_schema:
            try:
                import jsonschema
                jsonschema.validate(input_data, output_schema)
            except Exception as exc:
                return [{"type": "text", "text": f"Validation error: {exc}"}]

        return [{"type": "text", "text": json.dumps(input_data)}]


synthetic_output_tool = SyntheticOutputTool()
