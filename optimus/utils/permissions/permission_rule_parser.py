"""
Parses and serializes permission rule strings.
Mirrors src/utils/permissions/permissionRuleParser.ts
"""
from __future__ import annotations

from optimus.types.permissions import PermissionRuleValue

__all__ = [
    "escape_rule_content",
    "unescape_rule_content",
    "permission_rule_value_from_string",
    "permission_rule_value_to_string",
    "normalize_legacy_tool_name",
    "get_legacy_tool_names",
]

# Maps legacy tool names to their current canonical names.
# When a tool is renamed, add old -> new here.
_LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "Task": "Agent",
    "KillShell": "TaskStop",
    "AgentOutputTool": "TaskOutput",
    "BashOutputTool": "TaskOutput",
}


def normalize_legacy_tool_name(name: str) -> str:
    """Returns canonical tool name, resolving legacy aliases."""
    return _LEGACY_TOOL_NAME_ALIASES.get(name, name)


def get_legacy_tool_names(canonical_name: str) -> list[str]:
    """Returns all legacy names that map to the given canonical name."""
    return [legacy for legacy, canon in _LEGACY_TOOL_NAME_ALIASES.items() if canon == canonical_name]


def escape_rule_content(content: str) -> str:
    """Escapes special characters in rule content for safe storage.

    Escaping order matters:
    1. Escape existing backslashes first (\\ -> \\\\)
    2. Then escape parentheses (( -> \\(, ) -> \\))
    """
    content = content.replace("\\", "\\\\")
    content = content.replace("(", "\\(")
    content = content.replace(")", "\\)")
    return content


def unescape_rule_content(content: str) -> str:
    """Unescapes special characters in rule content after parsing.

    Unescaping order matters (reverse of escaping):
    1. Unescape parentheses first (\\( -> (, \\) -> ))
    2. Then unescape backslashes (\\\\ -> \\)
    """
    content = content.replace("\\(", "(")
    content = content.replace("\\)", ")")
    content = content.replace("\\\\", "\\")
    return content


def _find_first_unescaped_char(s: str, char: str) -> int:
    """Find the index of the first unescaped occurrence of char.
    A character is escaped if preceded by an odd number of backslashes."""
    for i, c in enumerate(s):
        if c == char:
            backslash_count = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                return i
    return -1


def _find_last_unescaped_char(s: str, char: str) -> int:
    """Find the index of the last unescaped occurrence of char."""
    for i in range(len(s) - 1, -1, -1):
        if s[i] == char:
            backslash_count = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                return i
    return -1


def permission_rule_value_from_string(rule_string: str) -> PermissionRuleValue:
    """Parses a permission rule string into its components.

    Format: "ToolName" or "ToolName(content)"
    Content may contain escaped parentheses: \\( and \\)

    Examples:
        'Bash'                            -> PermissionRuleValue('Bash')
        'Bash(npm install)'               -> PermissionRuleValue('Bash', 'npm install')
        'Bash(python -c "print\\\\(1\\\\)")' -> PermissionRuleValue('Bash', 'python -c "print(1)"')
    """
    open_paren = _find_first_unescaped_char(rule_string, "(")
    if open_paren == -1:
        return PermissionRuleValue(normalize_legacy_tool_name(rule_string))

    close_paren = _find_last_unescaped_char(rule_string, ")")
    if close_paren == -1 or close_paren <= open_paren:
        return PermissionRuleValue(normalize_legacy_tool_name(rule_string))

    if close_paren != len(rule_string) - 1:
        return PermissionRuleValue(normalize_legacy_tool_name(rule_string))

    tool_name = rule_string[:open_paren]
    raw_content = rule_string[open_paren + 1:close_paren]

    if not tool_name:
        return PermissionRuleValue(normalize_legacy_tool_name(rule_string))

    # Empty content ("Bash()") or standalone wildcard ("Bash(*)") -> tool-wide rule
    if raw_content in ("", "*"):
        return PermissionRuleValue(normalize_legacy_tool_name(tool_name))

    rule_content = unescape_rule_content(raw_content)
    return PermissionRuleValue(normalize_legacy_tool_name(tool_name), rule_content)


def permission_rule_value_to_string(rule_value: PermissionRuleValue) -> str:
    """Converts a permission rule value to its string representation.

    Examples:
        PermissionRuleValue('Bash')              -> 'Bash'
        PermissionRuleValue('Bash', 'npm install') -> 'Bash(npm install)'
    """
    if not rule_value.rule_content:
        return rule_value.tool_name
    escaped = escape_rule_content(rule_value.rule_content)
    return f"{rule_value.tool_name}({escaped})"
