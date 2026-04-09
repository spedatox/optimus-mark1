"""
Message factory functions and utilities.
Mirrors src/utils/messages.ts (core subset — factory functions, normalization,
string constants, and message predicate helpers).

The full TypeScript file is 5,500+ lines and includes UI rendering logic.
This port covers the behaviorally critical layer consumed by the agent loop.
"""
from __future__ import annotations

import re
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Any

from optimus.types.message import (
    AssistantMessage,
    AssistantMessageContent,
    ProgressMessage,
    SystemInformationalMessage,
    TombstoneMessage,
    UserMessage,
    UserMessageContent,
)

# ---------------------------------------------------------------------------
# String constants (exported — consumed by tool result rendering and agent loop)
# ---------------------------------------------------------------------------

NO_CONTENT_MESSAGE = "<no_content>"  # mirrors constants/messages.ts

INTERRUPT_MESSAGE = "[Request interrupted by user]"
INTERRUPT_MESSAGE_FOR_TOOL_USE = "[Request interrupted by user for tool use]"
CANCEL_MESSAGE = (
    "The user doesn't want to take this action right now. "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "To tell you how to proceed, the user said:\n"
)
SUBAGENT_REJECT_MESSAGE = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "Try a different approach or report the limitation to complete your task."
)
SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "The user said:\n"
)
PLAN_REJECTION_PREFIX = (
    "The agent proposed a plan that was rejected by the user. "
    "The user chose to stay in plan mode rather than proceed with implementation.\n\n"
    "Rejected plan:\n"
)
DENIAL_WORKAROUND_GUIDANCE = (
    "IMPORTANT: You *may* attempt to accomplish this action using other tools that might naturally be used to accomplish this goal, "
    "e.g. using head instead of cat. But you *should not* attempt to work around this denial in malicious ways, "
    "e.g. do not use your ability to run tests to execute non-test actions. "
    "You should only try to work around this restriction in reasonable ways that do not attempt to bypass the intent behind this denial. "
    "If you believe this capability is essential to complete the user's request, STOP and explain to the user "
    "what you were trying to do and why you need this permission. Let the user decide how to proceed."
)
NO_RESPONSE_REQUESTED = "No response requested."
SYNTHETIC_TOOL_RESULT_PLACEHOLDER = "[Tool result missing due to internal error]"
SYNTHETIC_MODEL = "<synthetic>"

SYNTHETIC_MESSAGES: frozenset[str] = frozenset([
    INTERRUPT_MESSAGE,
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    CANCEL_MESSAGE,
    REJECT_MESSAGE,
    NO_RESPONSE_REQUESTED,
])

_AUTO_MODE_REJECTION_PREFIX = "Permission for this action has been denied. Reason: "

# XML tag names used in message formatting
COMMAND_NAME_TAG = "command-name"
COMMAND_MESSAGE_TAG = "command-message"
COMMAND_ARGS_TAG = "command-args"
LOCAL_COMMAND_CAVEAT_TAG = "local-command-caveat"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_uuid() -> str:
    return str(_uuid_mod.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_default_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


# ---------------------------------------------------------------------------
# Message factories
# ---------------------------------------------------------------------------

def _base_create_assistant_message(
    *,
    content: list[dict[str, Any]],
    is_api_error_message: bool = False,
    api_error: Any = None,
    error: Any = None,
    error_details: str | None = None,
    is_virtual: bool | None = None,
    usage: dict[str, Any] | None = None,
) -> AssistantMessage:
    return AssistantMessage(
        type="assistant",
        uuid=_new_uuid(),
        timestamp=_now_iso(),
        message=AssistantMessageContent(
            id=_new_uuid(),
            model=SYNTHETIC_MODEL,
            role="assistant",
            stop_reason="stop_sequence",
            stop_sequence="",
            type="message",
            content=content,
            usage=usage or _make_default_usage(),
            container=None,
            context_management=None,
        ),
        request_id=None,
        api_error=api_error,
        error=error,
        error_details=error_details,
        is_api_error_message=is_api_error_message,
        is_virtual=is_virtual,
    )


def create_assistant_message(
    *,
    content: str | list[dict[str, Any]],
    usage: dict[str, Any] | None = None,
    is_virtual: bool | None = None,
) -> AssistantMessage:
    """Create a synthetic AssistantMessage from text or content blocks."""
    if isinstance(content, str):
        blocks: list[dict[str, Any]] = [{"type": "text", "text": content or NO_CONTENT_MESSAGE}]
    else:
        blocks = content
    return _base_create_assistant_message(content=blocks, usage=usage, is_virtual=is_virtual)


def create_assistant_api_error_message(
    *,
    content: str,
    api_error: Any = None,
    error: Any = None,
    error_details: str | None = None,
) -> AssistantMessage:
    return _base_create_assistant_message(
        content=[{"type": "text", "text": content or NO_CONTENT_MESSAGE}],
        is_api_error_message=True,
        api_error=api_error,
        error=error,
        error_details=error_details,
    )


def create_user_message(
    *,
    content: str | list[dict[str, Any]],
    is_meta: bool | None = None,
    is_visible_in_transcript_only: bool | None = None,
    is_virtual: bool | None = None,
    is_compact_summary: bool | None = None,
    summarize_metadata: Any = None,
    tool_use_result: Any = None,
    mcp_meta: Any = None,
    uuid: str | None = None,
    timestamp: str | None = None,
    image_paste_ids: list[int] | None = None,
    source_tool_assistant_uuid: str | None = None,
    permission_mode: Any = None,
    origin: str | None = None,
) -> UserMessage:
    """Create a UserMessage."""
    actual_content: Any = content or NO_CONTENT_MESSAGE
    return UserMessage(
        type="user",
        message=UserMessageContent(role="user", content=actual_content),
        uuid=uuid or _new_uuid(),
        timestamp=timestamp or _now_iso(),
        is_meta=is_meta,
        is_visible_in_transcript_only=is_visible_in_transcript_only,
        is_virtual=is_virtual,
        is_compact_summary=is_compact_summary,
        summarize_metadata=summarize_metadata,
        tool_use_result=tool_use_result,
        mcp_meta=mcp_meta,
        image_paste_ids=image_paste_ids,
        source_tool_assistant_uuid=source_tool_assistant_uuid,
        permission_mode=permission_mode,
        origin=origin,
    )


def prepare_user_content(
    *,
    input_string: str,
    preceding_input_blocks: list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    if not preceding_input_blocks:
        return input_string
    return [*preceding_input_blocks, {"text": input_string, "type": "text"}]


def create_user_interruption_message(*, tool_use: bool = False) -> UserMessage:
    content = INTERRUPT_MESSAGE_FOR_TOOL_USE if tool_use else INTERRUPT_MESSAGE
    return create_user_message(content=[{"type": "text", "text": content}])


def create_synthetic_user_caveat_message() -> UserMessage:
    return create_user_message(
        content=(
            f"<{LOCAL_COMMAND_CAVEAT_TAG}>Caveat: The messages below were generated by the user "
            f"while running local commands. DO NOT respond to these messages or otherwise consider "
            f"them in your response unless the user explicitly asks you to.</{LOCAL_COMMAND_CAVEAT_TAG}>"
        ),
        is_meta=True,
    )


def create_progress_message(
    *,
    tool_use_id: str,
    parent_tool_use_id: str,
    data: Any,
) -> ProgressMessage:
    return ProgressMessage(
        type="progress",
        data=data,
        tool_use_id=tool_use_id,
        parent_tool_use_id=parent_tool_use_id,
        uuid=_new_uuid(),
        timestamp=_now_iso(),
    )


def create_tool_result_stop_message(tool_use_id: str) -> dict[str, Any]:
    """Return a ToolResultBlockParam that cancels a tool use."""
    return {
        "type": "tool_result",
        "content": CANCEL_MESSAGE,
        "is_error": True,
        "tool_use_id": tool_use_id,
    }


# ---------------------------------------------------------------------------
# Message predicates
# ---------------------------------------------------------------------------

def is_synthetic_message(message: Any) -> bool:
    msg_type = getattr(message, "type", None)
    if msg_type in ("progress", "attachment", "system"):
        return False
    msg = getattr(message, "message", None)
    if not msg:
        return False
    content = getattr(msg, "content", None)
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    if not isinstance(first, dict):
        return False
    return first.get("type") == "text" and first.get("text") in SYNTHETIC_MESSAGES


def is_classifier_denial(content: str) -> bool:
    return content.startswith(_AUTO_MODE_REJECTION_PREFIX)


def is_tool_use_request_message(message: Any) -> bool:
    if getattr(message, "type", None) != "assistant":
        return False
    msg = getattr(message, "message", None)
    if not msg:
        return False
    content = getattr(msg, "content", None)
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        for b in content
    )


def is_tool_use_result_message(message: Any) -> bool:
    if getattr(message, "type", None) != "user":
        return False
    if getattr(message, "tool_use_result", None) is not None:
        return True
    msg = getattr(message, "message", None)
    if not msg:
        return False
    content = getattr(msg, "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        return isinstance(first, dict) and first.get("type") == "tool_result"
    return False


def is_not_empty_message(message: Any) -> bool:
    msg_type = getattr(message, "type", None)
    if msg_type in ("progress", "attachment", "system"):
        return True
    msg = getattr(message, "message", None)
    if not msg:
        return False
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    if not content:
        return False
    if len(content) > 1:
        return True
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        return True
    text = first.get("text", "")
    return (
        bool(text.strip())
        and text != NO_CONTENT_MESSAGE
        and text != INTERRUPT_MESSAGE_FOR_TOOL_USE
    )


def get_last_assistant_message(messages: list[Any]) -> Any | None:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "assistant":
            return msg
    return None


def has_tool_calls_in_last_assistant_turn(messages: list[Any]) -> bool:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "assistant":
            content = getattr(getattr(msg, "message", None), "content", None)
            if isinstance(content, list):
                return any(
                    isinstance(b, dict) and b.get("type") == "tool_use"
                    for b in content
                )
    return False


def get_assistant_message_text(message: Any) -> str | None:
    if getattr(message, "type", None) != "assistant":
        return None
    content = getattr(getattr(message, "message", None), "content", None)
    if not isinstance(content, list):
        return None
    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(texts) if texts else None


def get_user_message_text(message: Any) -> str | None:
    if getattr(message, "type", None) != "user":
        return None
    content = getattr(getattr(message, "message", None), "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


# ---------------------------------------------------------------------------
# UUID utilities
# ---------------------------------------------------------------------------

def derive_uuid(parent_uuid: str, index: int) -> str:
    """Deterministically derive a UUID from parent UUID + index."""
    hex_idx = format(index, "012x")
    return f"{parent_uuid[:24]}{hex_idx}"


def derive_short_message_id(uuid: str) -> str:
    """Derive a 6-char base36 short ID from a UUID."""
    hex_str = uuid.replace("-", "")[:10]
    num = int(hex_str, 16)
    return _to_base36(num)[:6]


def _to_base36(n: int) -> str:
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []
    while n:
        result.append(digits[n % 36])
        n //= 36
    return "".join(reversed(result))


# ---------------------------------------------------------------------------
# Message normalization
# ---------------------------------------------------------------------------

def normalize_messages(messages: list[Any]) -> list[Any]:
    """
    Split messages so each content block gets its own message.
    Mirrors normalizeMessages() in messages.ts — critical for API submission.
    """
    is_new_chain = False
    result: list[Any] = []

    for message in messages:
        msg_type = getattr(message, "type", None)

        if msg_type == "assistant":
            content = getattr(getattr(message, "message", None), "content", [])
            if not isinstance(content, list):
                result.append(message)
                continue
            is_new_chain = is_new_chain or len(content) > 1
            for i, block in enumerate(content):
                new_uuid = derive_uuid(message.uuid, i) if is_new_chain else message.uuid
                import dataclasses
                new_msg_content = dataclasses.replace(
                    message.message,
                    content=[block],
                )
                result.append(dataclasses.replace(message, message=new_msg_content, uuid=new_uuid))

        elif msg_type == "user":
            msg_content = getattr(getattr(message, "message", None), "content", None)
            if isinstance(msg_content, str):
                new_uuid = derive_uuid(message.uuid, 0) if is_new_chain else message.uuid
                import dataclasses
                result.append(dataclasses.replace(
                    message,
                    uuid=new_uuid,
                    message=dataclasses.replace(
                        message.message,
                        content=[{"type": "text", "text": msg_content}],
                    ),
                ))
            elif isinstance(msg_content, list):
                is_new_chain = is_new_chain or len(msg_content) > 1
                image_index = 0
                for i, block in enumerate(msg_content):
                    is_image = isinstance(block, dict) and block.get("type") == "image"
                    image_id: int | None = None
                    if is_image and message.image_paste_ids:
                        image_id = message.image_paste_ids[image_index] if image_index < len(message.image_paste_ids) else None
                        image_index += 1
                    new_uuid = derive_uuid(message.uuid, i) if is_new_chain else message.uuid
                    result.append(create_user_message(
                        content=[block],
                        tool_use_result=message.tool_use_result,
                        mcp_meta=message.mcp_meta,
                        is_meta=message.is_meta,
                        is_visible_in_transcript_only=message.is_visible_in_transcript_only,
                        is_virtual=message.is_virtual,
                        timestamp=message.timestamp,
                        image_paste_ids=[image_id] if image_id is not None else None,
                        origin=message.origin,
                        uuid=new_uuid,
                    ))
            else:
                result.append(message)

        else:
            result.append(message)

    return result


# ---------------------------------------------------------------------------
# XML tag extraction
# ---------------------------------------------------------------------------

def extract_tag(html: str, tag_name: str) -> str | None:
    """Extract the content of an XML-like tag from a string."""
    if not html.strip() or not tag_name.strip():
        return None
    escaped = re.escape(tag_name)
    pattern = re.compile(
        rf"<{escaped}(?:\s+[^>]*)?>[\s\S]*?</{escaped}>",
        re.IGNORECASE,
    )
    inner_pattern = re.compile(
        rf"<{escaped}(?:\s+[^>]*)?>([\s\S]*?)</{escaped}>",
        re.IGNORECASE,
    )
    for m in inner_pattern.finditer(html):
        content = m.group(1)
        if content:
            return content
    return None


# ---------------------------------------------------------------------------
# Rejection message builders
# ---------------------------------------------------------------------------

def auto_reject_message(tool_name: str) -> str:
    return f"Permission to use {tool_name} has been denied. {DENIAL_WORKAROUND_GUIDANCE}"


def dont_ask_reject_message(tool_name: str) -> str:
    return (
        f"Permission to use {tool_name} has been denied because Claude Code is running "
        f"in don't ask mode. {DENIAL_WORKAROUND_GUIDANCE}"
    )


def build_yolo_rejection_message(reason: str) -> str:
    try:
        from optimus.utils.features import feature
        has_bash_classifier = feature("BASH_CLASSIFIER")
    except Exception:
        has_bash_classifier = False

    rule_hint = (
        "To allow this type of action in the future, the user can add a permission rule like "
        "Bash(prompt: <description of allowed action>) to their settings. "
        "At the end of your session, recommend what permission rules to add so you don't get blocked again."
        if has_bash_classifier
        else "To allow this type of action in the future, the user can add a Bash permission rule to their settings."
    )

    return (
        f"{_AUTO_MODE_REJECTION_PREFIX}{reason}. "
        f"If you have other tasks that don't depend on this action, continue working on those. "
        f"{DENIAL_WORKAROUND_GUIDANCE} "
        f"{rule_hint}"
    )


def build_classifier_unavailable_message(tool_name: str, classifier_model: str) -> str:
    return (
        f"{classifier_model} is temporarily unavailable, so auto mode cannot determine "
        f"the safety of {tool_name} right now. "
        f"Wait briefly and then try this action again. "
        f"If it keeps failing, continue with other tasks that don't require this action and come back to it later. "
        f"Note: reading files, searching code, and other read-only operations do not require the classifier and can still be used."
    )


# ---------------------------------------------------------------------------
# Command formatting
# ---------------------------------------------------------------------------

def format_command_input_tags(command_name: str, args: str) -> str:
    return (
        f"<{COMMAND_NAME_TAG}>/{command_name}</{COMMAND_NAME_TAG}>\n"
        f"<{COMMAND_MESSAGE_TAG}>{command_name}</{COMMAND_MESSAGE_TAG}>\n"
        f"<{COMMAND_ARGS_TAG}>{args}</{COMMAND_ARGS_TAG}>"
    )


# ---------------------------------------------------------------------------
# System message helpers
# ---------------------------------------------------------------------------

def wrap_in_system_reminder(content: str) -> str:
    return f"<system-reminder>\n{content}\n</system-reminder>"


def wrap_messages_in_system_reminder(messages: list[str]) -> str:
    joined = "\n".join(messages)
    return wrap_in_system_reminder(joined)


# ---------------------------------------------------------------------------
# Tool result helpers
# ---------------------------------------------------------------------------

def get_tool_use_id(message: Any) -> str | None:
    if getattr(message, "type", None) != "user":
        return None
    content = getattr(getattr(message, "message", None), "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "tool_result":
            return first.get("tool_use_id")
    return None


def get_tool_result_ids(normalized_messages: list[Any]) -> dict[str, str]:
    """Return mapping of tool_use_id -> result message uuid."""
    result: dict[str, str] = {}
    for msg in normalized_messages:
        tid = get_tool_use_id(msg)
        if tid:
            result[tid] = msg.uuid
    return result


# ---------------------------------------------------------------------------
# Memory hint
# ---------------------------------------------------------------------------

def with_memory_correction_hint(message: str) -> str:
    try:
        from optimus.memdir.paths import is_auto_memory_enabled
        from optimus.services.analytics.growthbook import get_feature_value_cached
        if is_auto_memory_enabled() and get_feature_value_cached("tengu_amber_prism", False):
            return message + "\n\n[Memory correction hint: if you find you made an error, update your memory accordingly.]"
    except Exception:
        pass
    return message
