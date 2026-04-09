"""
Core agent query loop — streaming API calls + tool dispatch.
Mirrors src/query.ts (essential agentic loop; advanced features like
auto-compaction, token budget, reactive-compact are stubbed for later).
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from optimus.utils.debug import log_for_debugging
from optimus.utils.messages import (
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    create_user_message,
)

# Maximum turns per query (matches TS default)
DEFAULT_MAX_TURNS = 100

# ToolUseContext is passed through to individual tools
from optimus.tool import ToolUseContext


async def query(
    *,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]],
    tools: list[Any],
    tool_use_context: ToolUseContext,
    model: str = "claude-opus-4-5-20251101",
    max_tokens: int = 16000,
    max_turns: int = DEFAULT_MAX_TURNS,
    abort_event: asyncio.Event | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Run the agentic query loop. Yields stream events as dicts.

    Each yielded dict has a `type` field:
      "assistant"        — full assistant message (after streaming completes)
      "user"             — tool result message added to conversation
      "stream_text"      — streaming text delta
      "stream_thinking"  — streaming thinking delta
      "tool_use_start"   — tool call beginning
      "tool_result"      — tool call result
      "error"            — API or tool error
      "done"             — loop finished (includes stop_reason)
    """
    return _query_loop(
        messages=messages,
        system=system,
        tools=tools,
        tool_use_context=tool_use_context,
        model=model,
        max_tokens=max_tokens,
        max_turns=max_turns,
        abort_event=abort_event,
    )


async def _query_loop(
    *,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]],
    tools: list[Any],
    tool_use_context: ToolUseContext,
    model: str,
    max_tokens: int,
    max_turns: int,
    abort_event: asyncio.Event | None,
) -> AsyncGenerator[dict[str, Any], None]:
    client = anthropic.AsyncAnthropic()

    # Convert tool objects to API schema dicts
    api_tools: list[dict[str, Any]] = []
    tool_map: dict[str, Any] = {}
    for t in tools:
        api_tools.append({
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        })
        tool_map[t.name] = t

    current_messages = list(messages)
    turn = 0

    while turn < max_turns:
        if abort_event and abort_event.is_set():
            yield {"type": "done", "stop_reason": "aborted"}
            return

        turn += 1
        log_for_debugging(f"query: turn {turn}, messages={len(current_messages)}")

        # ---- streaming API call ----
        assistant_content: list[dict[str, Any]] = []
        input_tokens = 0
        output_tokens = 0

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=current_messages,
                tools=api_tools or anthropic.NOT_GIVEN,
            ) as stream:
                async for event in stream:
                    if abort_event and abort_event.is_set():
                        break

                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "text":
                            assistant_content.append({"type": "text", "text": ""})
                        elif block.type == "thinking":
                            assistant_content.append({"type": "thinking", "thinking": ""})
                        elif block.type == "tool_use":
                            assistant_content.append({
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": {},
                            })
                            yield {"type": "tool_use_start", "name": block.name, "id": block.id}

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        idx = event.index
                        if delta.type == "text_delta":
                            if idx < len(assistant_content) and assistant_content[idx]["type"] == "text":
                                assistant_content[idx]["text"] += delta.text
                            yield {"type": "stream_text", "text": delta.text}
                        elif delta.type == "thinking_delta":
                            if idx < len(assistant_content) and assistant_content[idx]["type"] == "thinking":
                                assistant_content[idx]["thinking"] += delta.thinking
                            yield {"type": "stream_thinking", "thinking": delta.thinking}
                        elif delta.type == "input_json_delta":
                            # Accumulate raw JSON string for tool input
                            block = assistant_content[idx] if idx < len(assistant_content) else None
                            if block and block["type"] == "tool_use":
                                block.setdefault("_raw_input", "")
                                block["_raw_input"] += delta.partial_json

                    elif event.type == "message_delta":
                        if hasattr(event, "usage"):
                            output_tokens = event.usage.output_tokens or 0

                    elif event.type == "message_start":
                        if hasattr(event.message, "usage"):
                            input_tokens = event.message.usage.input_tokens or 0

                final_msg = await stream.get_final_message()
                stop_reason = final_msg.stop_reason

        except anthropic.APIStatusError as exc:
            log_for_debugging(f"query: API error {exc.status_code}: {exc.message}", level="error")
            yield {"type": "error", "error": str(exc), "status_code": exc.status_code}
            return
        except Exception as exc:
            log_for_debugging(f"query: unexpected error: {exc}", level="error")
            yield {"type": "error", "error": str(exc)}
            return

        # Parse accumulated tool input JSON
        tool_uses: list[dict[str, Any]] = []
        for block in assistant_content:
            if block["type"] == "tool_use" and "_raw_input" in block:
                import json
                try:
                    block["input"] = json.loads(block["_raw_input"])
                except json.JSONDecodeError:
                    block["input"] = {}
                del block["_raw_input"]
            if block["type"] == "tool_use":
                tool_uses.append(block)

        # Emit full assistant message
        assistant_uuid = str(uuid.uuid4())
        assistant_msg: dict[str, Any] = {
            "type": "assistant",
            "uuid": assistant_uuid,
            "content": assistant_content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        yield assistant_msg
        current_messages.append({"role": "assistant", "content": assistant_content})

        if abort_event and abort_event.is_set():
            yield {"type": "done", "stop_reason": "aborted"}
            return

        if stop_reason == "end_turn" or not tool_uses:
            yield {"type": "done", "stop_reason": stop_reason or "end_turn"}
            return

        if stop_reason != "tool_use":
            yield {"type": "done", "stop_reason": stop_reason or "end_turn"}
            return

        # ---- dispatch tool calls ----
        tool_results: list[dict[str, Any]] = []

        for tool_use in tool_uses:
            tool_name = tool_use["name"]
            tool_id = tool_use["id"]
            tool_input = tool_use["input"]

            tool = tool_map.get(tool_name)
            if tool is None:
                error_text = f"Unknown tool: {tool_name}"
                log_for_debugging(f"query: {error_text}", level="warn")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": error_text,
                    "is_error": True,
                })
                yield {"type": "tool_result", "tool_use_id": tool_id, "name": tool_name, "error": error_text}
                continue

            # Permission check
            try:
                perm = await tool.check_permissions(tool_input, tool_use_context)
                if not perm.allowed:
                    msg = perm.message or f"Permission denied for tool: {tool_name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": msg,
                        "is_error": True,
                    })
                    yield {"type": "tool_result", "tool_use_id": tool_id, "name": tool_name, "error": msg}
                    continue
            except Exception as exc:
                log_for_debugging(f"query: permission check error for {tool_name}: {exc}", level="error")

            # Execute tool
            try:
                result_blocks = await tool.call(tool_input, tool_use_context)
                content: str | list[dict[str, Any]] = result_blocks
                is_error = False
            except Exception as exc:
                log_for_debugging(f"query: tool {tool_name} error: {exc}", level="error")
                content = str(exc)
                is_error = True

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": content,
                "is_error": is_error,
            })
            yield {"type": "tool_result", "tool_use_id": tool_id, "name": tool_name, "is_error": is_error}

        # Add tool results as a user message
        user_tool_msg: dict[str, Any] = {"role": "user", "content": tool_results}
        current_messages.append(user_tool_msg)
        yield {"type": "user", "content": tool_results}

    # Exceeded max turns
    yield {"type": "done", "stop_reason": "max_turns"}
