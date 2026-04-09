"""
Debug filter — parse and apply debug category filters.
Mirrors src/utils/debugFilter.ts
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import NamedTuple


class DebugFilter(NamedTuple):
    include: list[str]
    exclude: list[str]
    is_exclusive: bool


@lru_cache(maxsize=None)
def parse_debug_filter(filter_string: str | None = None) -> DebugFilter | None:
    """
    Parse a debug filter string into a filter configuration.

    Examples:
      "api,hooks"  -> include only api and hooks categories
      "!1p,!file"  -> exclude logging and file categories
      None/""      -> no filtering (show all)
    """
    if not filter_string or not filter_string.strip():
        return None

    filters = [f.strip() for f in filter_string.split(",") if f.strip()]
    if not filters:
        return None

    has_exclusive = any(f.startswith("!") for f in filters)
    has_inclusive = any(not f.startswith("!") for f in filters)

    if has_exclusive and has_inclusive:
        # Mixed mode — unsupported, show all
        return None

    clean_filters = [f.lstrip("!").lower() for f in filters]

    return DebugFilter(
        include=[] if has_exclusive else clean_filters,
        exclude=clean_filters if has_exclusive else [],
        is_exclusive=has_exclusive,
    )


def extract_debug_categories(message: str) -> list[str]:
    """Extract debug categories from a message for filtering."""
    categories: list[str] = []

    # Pattern 3: MCP server "servername" — check first to avoid false positives
    mcp_match = re.match(r"""^MCP server ["']([^"']+)["']""", message)
    if mcp_match:
        categories.append("mcp")
        categories.append(mcp_match.group(1).lower())
    else:
        # Pattern 1: "category: message"
        prefix_match = re.match(r"^([^:\[]+):", message)
        if prefix_match:
            categories.append(prefix_match.group(1).strip().lower())

    # Pattern 2: [CATEGORY] at start
    bracket_match = re.match(r"^\[([^\]]+)\]", message)
    if bracket_match:
        categories.append(bracket_match.group(1).strip().lower())

    # Pattern 4: 1P event
    if "1p event:" in message.lower():
        categories.append("1p")

    # Pattern 5: secondary categories
    secondary_match = re.search(
        r":\s*([^:]+?)(?:\s+(?:type|mode|status|event))?:", message
    )
    if secondary_match:
        secondary = secondary_match.group(1).strip().lower()
        if len(secondary) < 30 and " " not in secondary:
            categories.append(secondary)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for c in categories:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def should_show_debug_categories(
    categories: list[str], filter_: DebugFilter | None
) -> bool:
    if not filter_:
        return True
    if not categories:
        return False
    if filter_.is_exclusive:
        return not any(c in filter_.exclude for c in categories)
    return any(c in filter_.include for c in categories)


def should_show_debug_message(message: str, filter_: DebugFilter | None) -> bool:
    if not filter_:
        return True
    categories = extract_debug_categories(message)
    return should_show_debug_categories(categories, filter_)
