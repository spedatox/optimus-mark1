"""TaskRegistry — in-memory registry for background task handles."""
from __future__ import annotations
import asyncio
from typing import Any, Protocol


class TaskHandle(Protocol):
    task_type: str
    status: str
    description: str

    async def stop(self) -> None: ...
    async def wait(self) -> None: ...
    async def get_output(self) -> str: ...
    def get_partial_output(self) -> str: ...


_registry: dict[str, Any] = {}


def get_task_registry() -> dict[str, Any]:
    return _registry


def register_task(task_id: str, handle: Any) -> None:
    _registry[task_id] = handle


def unregister_task(task_id: str) -> None:
    _registry.pop(task_id, None)
