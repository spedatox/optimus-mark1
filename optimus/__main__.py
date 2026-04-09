"""
OPTIMUS Mark I — CLI entry point.
Mirrors src/entrypoints/cli.tsx (core REPL and non-interactive modes).

Usage:
  optimus                  Interactive REPL
  optimus "prompt"         Single-turn non-interactive
  optimus --help           Show help
  optimus --version        Show version
  optimus --debug          Enable debug logging
  optimus --print "prompt" Print response and exit (non-interactive)
"""
from __future__ import annotations

import asyncio
import os
import sys

import click

__version__ = "0.1.0"


def _get_tools() -> list:
    from optimus.tools import get_all_tools
    return get_all_tools()


def _get_system_prompt() -> str:
    return (
        "You are an expert software engineer. "
        "Use the available tools to help the user with coding tasks. "
        "Be concise and precise. Always prefer dedicated tools over bash for file operations."
    )


async def _run_single_turn(prompt: str, debug: bool) -> None:
    if debug:
        from optimus.utils.debug import enable_debug_logging
        enable_debug_logging()

    from optimus.query import query
    from optimus.tool import ToolUseContext
    from optimus.bootstrap.state import get_session_id
    from optimus.utils.cwd import get_cwd

    tools = _get_tools()
    ctx = ToolUseContext(
        session_id=get_session_id(),
        cwd=get_cwd(),
        permission_mode="default",
    )

    messages = [{"role": "user", "content": prompt}]
    system = _get_system_prompt()

    async for event in await query(
        messages=messages,
        system=system,
        tools=tools,
        tool_use_context=ctx,
    ):
        etype = event.get("type")
        if etype == "stream_text":
            print(event["text"], end="", flush=True)
        elif etype == "tool_use_start":
            print(f"\n[Tool: {event['name']}]", flush=True)
        elif etype == "tool_result":
            pass  # tool output is folded into next assistant turn
        elif etype == "error":
            print(f"\nError: {event['error']}", file=sys.stderr)
        elif etype == "done":
            print()  # final newline


async def _run_repl(debug: bool) -> None:
    if debug:
        from optimus.utils.debug import enable_debug_logging
        enable_debug_logging()

    from optimus.query import query
    from optimus.tool import ToolUseContext
    from optimus.bootstrap.state import get_session_id
    from optimus.utils.cwd import get_cwd
    from optimus.history import add_to_history

    tools = _get_tools()
    system = _get_system_prompt()
    conversation: list[dict] = []

    click.echo(f"OPTIMUS Mark I v{__version__} — type /exit or Ctrl-C to quit\n")

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nGoodbye.")
            break

        stripped = user_input.strip()
        if not stripped:
            continue
        if stripped in ("/exit", "/quit", "exit", "quit"):
            click.echo("Goodbye.")
            break

        add_to_history(stripped)

        ctx = ToolUseContext(
            session_id=get_session_id(),
            cwd=get_cwd(),
            permission_mode="default",
        )

        conversation.append({"role": "user", "content": stripped})

        print("Assistant: ", end="", flush=True)
        assistant_text = ""

        async for event in await query(
            messages=list(conversation),
            system=system,
            tools=tools,
            tool_use_context=ctx,
        ):
            etype = event.get("type")
            if etype == "stream_text":
                t = event["text"]
                print(t, end="", flush=True)
                assistant_text += t
            elif etype == "tool_use_start":
                print(f"\n[Running: {event['name']}]", flush=True)
            elif etype == "error":
                print(f"\nError: {event['error']}", file=sys.stderr)
            elif etype == "done":
                print()

        if assistant_text:
            conversation.append({"role": "assistant", "content": assistant_text})


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version", prog_name="optimus")
@click.argument("prompt", required=False, default=None)
@click.option("--print", "-p", "print_mode", is_flag=True, help="Non-interactive: print response and exit.")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging.")
@click.option("--model", default=None, help="Override the model to use.")
def main(prompt: str | None, print_mode: bool, debug: bool, model: str | None) -> None:
    """OPTIMUS Mark I — autonomous Python coding agent."""
    if model:
        os.environ["OPTIMUS_MODEL"] = model

    if prompt or print_mode:
        text = prompt or click.get_text_stream("stdin").read()
        asyncio.run(_run_single_turn(text, debug=debug))
    else:
        asyncio.run(_run_repl(debug=debug))


if __name__ == "__main__":
    main()
