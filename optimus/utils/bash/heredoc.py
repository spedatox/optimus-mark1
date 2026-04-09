"""
Heredoc extraction and restoration utilities.

Faithful Python port of src/utils/bash/heredoc.ts.

The shell-quote / shlex library parses ``<<`` as two separate ``<`` redirect
operators which breaks command splitting for heredoc syntax.  This module
extracts heredocs before parsing and restores them afterwards.

Supported heredoc variations:
  - ``<<WORD``       — basic heredoc
  - ``<<'WORD'``     — single-quoted delimiter (no variable expansion)
  - ``<<"WORD"``     — double-quoted delimiter (with variable expansion)
  - ``<<-WORD``      — dash prefix (strips leading tabs from content)
  - ``<<-'WORD'``    — combined dash and quoted delimiter

Security: This module implements all the paranoid checks from the TS source
(backtick/arithmetic-context bail-outs, odd-backslash guard, PST_EOFTOKEN
protection, nested-heredoc filtering, multiple-same-line-start guard).
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from typing import Optional

HEREDOC_PLACEHOLDER_PREFIX = "__HEREDOC_"
HEREDOC_PLACEHOLDER_SUFFIX = "__"


def _generate_placeholder_salt() -> str:
    """8 random bytes as hex (16 chars), matching TS randomBytes(8).toString('hex')."""
    return secrets.token_hex(8)


# SECURITY: must NOT match << inside <<< (herestring).
# Two alternatives for quoted vs unquoted delimiters.
# Group indices (1-based):
#   1 = optional dash (-)
#   2 = optional quote char (' or ")  [quoted alt]
#   3 = delimiter word              [quoted alt, may start with \]
#   4 = delimiter word              [unquoted alt]
_HEREDOC_START_RE = re.compile(
    r"(?<!<)<<(?!<)(-)?[ \t]*(?:(['\"])(\\?\w+)\2|\\?(\w+))"
)


@dataclass
class HeredocInfo:
    """Information about a single extracted heredoc."""
    full_text: str          # full heredoc text including operator and content
    delimiter: str          # delimiter word (without quotes)
    operator_start_index: int
    operator_end_index: int
    content_start_index: int
    content_end_index: int


@dataclass
class HeredocExtractionResult:
    processed_command: str
    heredocs: dict[str, HeredocInfo] = field(default_factory=dict)


def extract_heredocs(
    command: str,
    *,
    quoted_only: bool = False,
) -> HeredocExtractionResult:
    """
    Extract heredocs from a command string, replacing them with unique placeholders.

    Returns a HeredocExtractionResult with the processed command and a dict
    mapping placeholder → HeredocInfo.  Use restore_heredocs() to undo.
    """
    heredocs: dict[str, HeredocInfo] = {}

    if "<<" not in command:
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # ---- Security paranoia pre-validation ----
    # $'...' or $"..." (ANSI-C / locale quoting) — our scanner can't handle
    if re.search(r"\$['\"]", command):
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # Backtick before the first <<
    first_heredoc_pos = command.index("<<")
    if first_heredoc_pos > 0 and "`" in command[:first_heredoc_pos]:
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # Unbalanced (( before << → arithmetic context, << may be a bit-shift
    if first_heredoc_pos > 0:
        before = command[:first_heredoc_pos]
        open_arith = before.count("((")
        close_arith = before.count("))")
        if open_arith > close_arith:
            return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # ---- Incremental quote/comment scanner state ----
    scan_pos = 0
    scan_in_single = False
    scan_in_double = False
    scan_in_comment = False
    scan_dq_escape_next = False
    scan_pending_backslashes = 0

    def advance_scan(target: int) -> None:
        nonlocal scan_pos, scan_in_single, scan_in_double, scan_in_comment
        nonlocal scan_dq_escape_next, scan_pending_backslashes

        for i in range(scan_pos, target):
            ch = command[i]

            # Physical newline always clears comment state (quote-blind)
            if ch == "\n":
                scan_in_comment = False

            if scan_in_single:
                if ch == "'":
                    scan_in_single = False
                continue

            if scan_in_double:
                if scan_dq_escape_next:
                    scan_dq_escape_next = False
                    continue
                if ch == "\\":
                    scan_dq_escape_next = True
                    continue
                if ch == '"':
                    scan_in_double = False
                continue

            # Unquoted context — comment-blind quote tracking
            if ch == "\\":
                scan_pending_backslashes += 1
                continue

            escaped = (scan_pending_backslashes % 2) == 1
            scan_pending_backslashes = 0
            if escaped:
                continue

            if ch == "'":
                scan_in_single = True
            elif ch == '"':
                scan_in_double = True
            elif not scan_in_comment and ch == "#":
                scan_in_comment = True

        scan_pos = target

    heredoc_matches: list[HeredocInfo] = []
    skipped_ranges: list[tuple[int, int]] = []  # (contentStartIndex, contentEndIndex)

    for m in _HEREDOC_START_RE.finditer(command):
        start_index = m.start()

        advance_scan(start_index)

        # Skip if inside a quoted string or comment
        if scan_in_single or scan_in_double or scan_in_comment:
            continue

        # Skip if preceded by odd number of backslashes
        if scan_pending_backslashes % 2 == 1:
            continue

        # Skip if inside a previously-skipped unquoted heredoc's body
        inside_skipped = any(
            cs < start_index < ce for cs, ce in skipped_ranges
        )
        if inside_skipped:
            continue

        is_dash = m.group(1) == "-"
        quote_char = m.group(2)          # group 2: ' or "
        delimiter = m.group(3) or m.group(4)  # group 3 (quoted) or 4 (unquoted)
        operator_end_index = m.end()

        # Validate that the quoted delimiter was actually closed by \2 in the regex
        if quote_char and command[operator_end_index - 1] != quote_char:
            continue

        # Determine if delimiter is quoted/escaped (→ heredoc body is literal)
        is_escaped_delimiter = "\\" in m.group(0)
        is_quoted_or_escaped = bool(quote_char) or is_escaped_delimiter

        # Verify next char is a bash metacharacter or end of string
        if operator_end_index < len(command):
            next_char = command[operator_end_index]
            if not re.match(r"^[ \t\n|&;()<>]$", next_char):
                continue

        # Find the first UNQUOTED newline after the operator
        first_newline_offset = _find_first_unquoted_newline(
            command, operator_end_index
        )
        if first_newline_offset == -1:
            continue

        # Security: bail if same-line content ends with odd backslash count
        same_line_content = command[operator_end_index: operator_end_index + first_newline_offset]
        trailing_bs = 0
        for ch in reversed(same_line_content):
            if ch == "\\":
                trailing_bs += 1
            else:
                break
        if trailing_bs % 2 == 1:
            continue

        content_start_index = operator_end_index + first_newline_offset
        after_newline = command[content_start_index + 1:]  # skip the newline itself
        content_lines = after_newline.split("\n")

        # Find closing delimiter line
        closing_line_index = _find_closing_delimiter(
            content_lines, delimiter, is_dash
        )

        # Handle quotedOnly mode for unquoted heredocs
        if quoted_only and not is_quoted_or_escaped:
            if closing_line_index == -1:
                skip_end = len(command)
            else:
                lines_up = content_lines[: closing_line_index + 1]
                skip_end = content_start_index + 1 + len("\n".join(lines_up))
            skipped_ranges.append((content_start_index, skip_end))
            continue

        if closing_line_index == -1:
            continue

        # Calculate content end index
        lines_up = content_lines[: closing_line_index + 1]
        content_length = len("\n".join(lines_up))
        content_end_index = content_start_index + 1 + content_length

        # Security: bail if overlaps with any skipped range
        overlaps = any(
            content_start_index < ce and cs < content_end_index
            for cs, ce in skipped_ranges
        )
        if overlaps:
            continue

        operator_text = command[start_index:operator_end_index]
        content_text = command[content_start_index:content_end_index]
        full_text = operator_text + content_text

        heredoc_matches.append(HeredocInfo(
            full_text=full_text,
            delimiter=delimiter,
            operator_start_index=start_index,
            operator_end_index=operator_end_index,
            content_start_index=content_start_index,
            content_end_index=content_end_index,
        ))

    if not heredoc_matches:
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # Filter out nested heredocs
    top_level = [
        h for h in heredoc_matches
        if not any(
            other is not h
            and other.content_start_index < h.operator_start_index < other.content_end_index
            for other in heredoc_matches
        )
    ]
    if not top_level:
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # Guard: multiple heredocs sharing the same content start position
    start_positions = {h.content_start_index for h in top_level}
    if len(start_positions) < len(top_level):
        return HeredocExtractionResult(processed_command=command, heredocs=heredocs)

    # Sort descending by content_end_index so we replace from end to start
    top_level.sort(key=lambda h: h.content_end_index, reverse=True)

    salt = _generate_placeholder_salt()
    processed = command

    for idx, info in enumerate(top_level):
        placeholder_index = len(top_level) - 1 - idx
        placeholder = (
            f"{HEREDOC_PLACEHOLDER_PREFIX}{placeholder_index}_{salt}"
            f"{HEREDOC_PLACEHOLDER_SUFFIX}"
        )
        heredocs[placeholder] = info

        # Replace: keep same-line content between operator and content start
        processed = (
            processed[: info.operator_start_index]
            + placeholder
            + processed[info.operator_end_index: info.content_start_index]
            + processed[info.content_end_index:]
        )

    return HeredocExtractionResult(processed_command=processed, heredocs=heredocs)


def restore_heredocs(parts: list[str], heredocs: dict[str, HeredocInfo]) -> list[str]:
    """
    Restore heredoc placeholders in a list of strings.

    Mirrors restoreHeredocs() from heredoc.ts.
    """
    if not heredocs:
        return parts
    return [_restore_in_string(p, heredocs) for p in parts]


def _restore_in_string(text: str, heredocs: dict[str, HeredocInfo]) -> str:
    for placeholder, info in heredocs.items():
        text = text.replace(placeholder, info.full_text)
    return text


def contains_heredoc(command: str) -> bool:
    """Quick check — does command contain heredoc syntax?"""
    return bool(_HEREDOC_START_RE.search(command))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_first_unquoted_newline(command: str, start: int) -> int:
    """
    Find the first newline after *start* that is NOT inside a quoted string.

    Returns the offset from *start*, or -1 if not found (quote never closes).
    """
    in_single = False
    in_double = False
    i = start
    while i < len(command):
        ch = command[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2  # skip escaped char
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        # Unquoted
        if ch == "\n":
            return i - start
        bs_count = 0
        j = i - 1
        while j >= start and command[j] == "\\":
            bs_count += 1
            j -= 1
        if bs_count % 2 == 1:
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        i += 1

    # Ended while inside a quote → no valid heredoc
    if in_single or in_double:
        return -1
    return -1  # no newline found


def _find_closing_delimiter(
    content_lines: list[str],
    delimiter: str,
    is_dash: bool,
) -> int:
    """
    Find the index of the line that is the closing delimiter.

    Returns -1 if not found or if a PST_EOFTOKEN-like early-close pattern is
    detected.
    """
    for i, line in enumerate(content_lines):
        check_line = line.lstrip("\t") if is_dash else line

        if check_line == delimiter:
            return i

        # PST_EOFTOKEN / metacharacter after delimiter → bail
        if (
            len(check_line) > len(delimiter)
            and check_line.startswith(delimiter)
        ):
            char_after = check_line[len(delimiter)]
            if re.match(r"^[)}`|&;(<>]$", char_after):
                return -1

    return -1
