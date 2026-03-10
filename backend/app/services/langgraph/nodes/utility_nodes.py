"""Utility nodes for logging, persistence, and failure handling.

These are direct ports of the existing orchestrator._log() and related
helpers, preserving the isolated-session pattern.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import async_session
from app.models import LogEntry, LogLevel, Task, TaskStatus
from app.services.logger import log_broadcaster
from app.services.langgraph.state import TaskState


async def log_step(
    task_id: int,
    message: str,
    level: str = "info",
    source: str = "orchestrator",
) -> None:
    """Write a log entry to DB and broadcast via WebSocket.

    Uses its own isolated DB session — never touches the caller's session.
    Direct port of orchestrator._log().
    """
    async with async_session() as log_session:
        entry = LogEntry(
            task_id=task_id,
            level=LogLevel(level),
            source=source,
            message=message,
        )
        log_session.add(entry)
        await log_session.commit()
    await log_broadcaster.broadcast(
        message=message, level=level, source=source, task_id=task_id,
    )


async def persist_result_node(state: TaskState) -> dict:
    """Write final_output and task_status back to the Task DB record.

    Called as the final node in each strategy graph.
    """
    task_id = state["task_id"]
    final_output = state.get("final_output")
    task_status = state.get("task_status", "completed")

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task:
            task.final_output = final_output
            task.status = TaskStatus(task_status)
            if task_status == "completed":
                task.completed_at = datetime.now(timezone.utc)
            await session.commit()

    await log_step(task_id, f"Task #{task_id} finished — status: {task_status}")
    return {}


async def fail_node(state: TaskState) -> dict:
    """Terminal failure node — marks task as failed."""
    error = state.get("error", "Unknown error")
    return {
        "task_status": "failed",
        "final_output": error,
    }
