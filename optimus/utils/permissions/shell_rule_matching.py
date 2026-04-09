"""
Shared permission rule matching utilities for shell tools.
Mirrors src/utils/permissions/shellRuleMatching.ts
"""
from __future__ import annotations

import re
from typing import Literal, Union

__all__ = [
    "ShellPermissionRule",
    "ExactRule",
    "PrefixRule",
    "WildcardRule",
    "permission_rule_extract_prefix",
    "has_wildcards",
    "match_wildcard_pattern",
    "parse_permission_rule",
    "suggestion_for_exact_command",
    "suggestion_for_prefix",
]


class ExactRule:
    type: Literal["exact"] = "exact"

    def __init__(self, command: str) -> None:
        self.type = "exact"
        self.command = command


class PrefixRule:
    type: Literal["prefix"] = "prefix"

    def __init__(self, prefix: str) -> None:
        self.type = "prefix"
        self.prefix = prefix


class WildcardRule:
    type: Literal["wildcard"] = "wildcard"

    def __init__(self, pattern: str) -> None:
        self.type = "wildcard"
        self.pattern = pattern


ShellPermissionRule = Union[ExactRule, PrefixRule, WildcardRule]

_ESCAPED_STAR_PLACEHOLDER = "\x00ESCAPED_STAR\x00"
_ESCAPED_BACKSLASH_PLACEHOLDER = "\x00ESCAPED_BACKSLASH\x00"


def permission_rule_extract_prefix(permission_rule: str) -> str | None:
    """Extract prefix from legacy :* syntax (e.g., "npm:*" -> "npm")."""
    m = re.match(r"^(.+):\*$", permission_rule)
    return m.group(1) if m else None


def has_wildcards(pattern: str) -> bool:
    """Check if a pattern contains unescaped wildcards (not legacy :* syntax)."""
    if pattern.endswith(":*"):
        return False
    i = 0
    while i < len(pattern):
        if pattern[i] == "*":
            backslash_count = 0
            j = i - 1
            while j >= 0 and pattern[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                return True
        i += 1
    return False


def match_wildcard_pattern(pattern: str, command: str, case_insensitive: bool = False) -> bool:
    """Match a command against a wildcard pattern.

    Wildcards (*) match any sequence of characters.
    Use \\* to match a literal asterisk character.
    Use \\\\ to match a literal backslash.
    """
    trimmed = pattern.strip()

    # Process the pattern to handle escape sequences: \\* and \\\\
    processed = ""
    i = 0
    while i < len(trimmed):
        char = trimmed[i]
        if char == "\\" and i + 1 < len(trimmed):
            next_char = trimmed[i + 1]
            if next_char == "*":
                processed += _ESCAPED_STAR_PLACEHOLDER
                i += 2
                continue
            elif next_char == "\\":
                processed += _ESCAPED_BACKSLASH_PLACEHOLDER
                i += 2
                continue
        processed += char
        i += 1

    # Escape regex special characters except *
    escaped = re.sub(r"[.+?^${}()|[\]\\'\"']", lambda m: "\\" + m.group(0), processed)

    # Convert unescaped * to .* for wildcard matching
    with_wildcards = escaped.replace("*", ".*")

    # Restore placeholders as escaped regex literals
    regex_pattern = (
        with_wildcards
        .replace(_ESCAPED_STAR_PLACEHOLDER, r"\*")
        .replace(_ESCAPED_BACKSLASH_PLACEHOLDER, r"\\")
    )

    # Count unescaped stars in processed (before regex conversion)
    unescaped_star_count = processed.count("*")

    # If pattern ends with ' *' and that's the only wildcard, make trailing space+args optional
    if regex_pattern.endswith(" .*") and unescaped_star_count == 1:
        regex_pattern = regex_pattern[:-3] + "( .*)?"

    flags = re.DOTALL | (re.IGNORECASE if case_insensitive else 0)
    try:
        return bool(re.fullmatch(regex_pattern, command, flags))
    except re.error:
        return False


def parse_permission_rule(permission_rule: str) -> ShellPermissionRule:
    """Parse a permission rule string into a structured rule object."""
    prefix = permission_rule_extract_prefix(permission_rule)
    if prefix is not None:
        return PrefixRule(prefix)
    if has_wildcards(permission_rule):
        return WildcardRule(permission_rule)
    return ExactRule(permission_rule)


def suggestion_for_exact_command(tool_name: str, command: str) -> list[dict]:
    """Generate permission update suggestion for an exact command match."""
    return [
        {
            "type": "addRules",
            "rules": [{"toolName": tool_name, "ruleContent": command}],
            "behavior": "allow",
            "destination": "localSettings",
        }
    ]


def suggestion_for_prefix(tool_name: str, prefix: str) -> list[dict]:
    """Generate permission update suggestion for a prefix match."""
    return [
        {
            "type": "addRules",
            "rules": [{"toolName": tool_name, "ruleContent": f"{prefix}:*"}],
            "behavior": "allow",
            "destination": "localSettings",
        }
    ]
