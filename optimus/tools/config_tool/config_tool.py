"""ConfigTool — get or set Optimus settings (theme, model, permissions)."""
from __future__ import annotations
import json
from typing import Any
from optimus.tool import Tool, ToolUseContext, ValidationResult

CONFIG_TOOL_NAME = "Config"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "setting": {
            "type": "string",
            "description": 'The setting key (e.g., "theme", "model", "permissions.defaultMode").',
        },
        "value": {
            "description": "The new value. Omit to get current value.",
        },
    },
    "required": ["setting"],
}

DESCRIPTION = "Get or set Optimus configuration settings (theme, model, permission mode, etc.)."

# Supported settings map: key -> (type_hint, description)
_SUPPORTED_SETTINGS: dict[str, str] = {
    "model": "string",
    "theme": "string",
    "permissions.defaultMode": "string",
    "maxTokens": "number",
    "debug": "boolean",
}


class ConfigTool(Tool):
    name: str = CONFIG_TOOL_NAME
    description: str = DESCRIPTION
    input_schema: dict[str, Any] = INPUT_SCHEMA

    async def check_permissions(self, input_data: dict[str, Any], ctx: ToolUseContext) -> ValidationResult:
        return ValidationResult(allowed=True)

    async def call(self, input_data: dict[str, Any], ctx: ToolUseContext) -> list[dict[str, Any]]:
        from optimus.utils.config import get_config, save_config

        setting: str = input_data["setting"]
        value: Any = input_data.get("value")
        is_set = "value" in input_data

        config = get_config()

        # Resolve nested key (dot-separated)
        keys = setting.split(".")
        current: Any = config
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            else:
                current = None
                break

        if not is_set:
            result = {
                "success": True,
                "operation": "get",
                "setting": setting,
                "value": current,
            }
            return [{"type": "text", "text": json.dumps(result)}]

        # Set value
        previous = current
        obj = config
        for k in keys[:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
        try:
            save_config(config)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
            return [{"type": "text", "text": json.dumps(result)}]

        result = {
            "success": True,
            "operation": "set",
            "setting": setting,
            "previousValue": previous,
            "newValue": value,
        }
        return [{"type": "text", "text": json.dumps(result)}]


config_tool = ConfigTool()
