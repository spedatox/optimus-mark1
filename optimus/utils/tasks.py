"""Task list utilities — in-memory task store for TaskCreate/Get/Update/List tools."""
from __future__ import annotations
from typing import Any

_tasks: dict[str, dict[str, Any]] = {}

VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "deleted"}


def create_task(
    task_id: str,
    subject: str,
    description: str,
    active_form: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    task: dict[str, Any] = {
        "id": task_id,
        "subject": subject,
        "description": description,
        "status": "pending",
        "activeForm": active_form or f"Working on {subject}",
        "metadata": metadata or {},
        "blocks": [],
        "blockedBy": [],
    }
    _tasks[task_id] = task
    return task


def get_task(task_id: str) -> dict[str, Any] | None:
    return _tasks.get(task_id)


def update_task(task_id: str, **kwargs: Any) -> dict[str, Any]:
    task = _tasks.get(task_id)
    if task is None:
        raise KeyError(f"Task not found: {task_id}")
    for key, value in kwargs.items():
        if key in task:
            task[key] = value
    return task


def delete_task(task_id: str) -> None:
    _tasks.pop(task_id, None)


def list_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": t["id"],
            "subject": t["subject"],
            "status": t["status"],
            "blockedBy": t.get("blockedBy", []),
        }
        for t in _tasks.values()
        if t.get("status") != "deleted"
    ]


def clear_tasks() -> None:
    _tasks.clear()
