"""Lucy Orchestrator Engine — thin adapter over LangGraph."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Agent, Task, TaskStatus
from app.services.langgraph.executor import graph_executor
from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.utility_nodes import log_step


async def execute_task(
    session: AsyncSession,
    task: Task,
    agents: list[Agent],
    conversation_history: list[dict] | None = None,
    workspace_dir: str | None = None,
) -> None:
    """Main entry point — dispatch to LangGraph graph executor."""
    settings = get_settings()

    task.status = TaskStatus.RUNNING
    await session.flush()

    await log_step(task.id, f"Task #{task.id} started — strategy: {task.strategy.value}")

    # Determine workspace directory (session-scoped or task-scoped)
    if workspace_dir is None:
        session_id = getattr(task, "session_id", None)
        if session_id:
            workspace_dir = os.path.join(settings.workspace_base_dir, f"session_{session_id}")
        else:
            workspace_dir = os.path.join(settings.workspace_base_dir, f"task_{task.id}")
    os.makedirs(workspace_dir, exist_ok=True)

    try:
        agent_dicts = [
            {
                "id": a.id,
                "name": a.name,
                "endpoint": a.endpoint,
                "model_name": a.model_name,
                "role": a.role.value,
                "description": a.description,
                "capabilities": a.capabilities,
                "available_resources": a.available_resources,
                "hierarchy_level": a.hierarchy_level,
                "is_orchestrator": a.is_orchestrator,
            }
            for a in agents
        ]

        initial_state: TaskState = {
            "task_id": task.id,
            "prompt": task.prompt,
            "strategy": task.strategy.value,
            "agents": agent_dicts,
            "agent_responses": [],
            "current_step_order": 0,
            "routing_decision": None,
            "council_opinions": [],
            "council_reviews": [],
            "council_rankings": [],
            "label_to_agent": {},
            "project_id": getattr(task, "project_id", None),
            "session_id": getattr(task, "session_id", None),
            "conversation_history": conversation_history or [],
            "tool_calls": [],
            "workspace_dir": workspace_dir,
            "project_plan": None,
            "agent_allocation": None,
            "task_breakdown": [],
            "manager_checklists": {},
            "hierarchy_results": [],
            "rework_count": 0,
            "rework_needed": False,
            "final_output": None,
            "structured_output": None,
            "task_status": "running",
            "error": None,
        }

        result = await graph_executor.run(initial_state)

        task.final_output = result.get("final_output")
        task_status = result.get("task_status", "completed")
        task.status = TaskStatus(task_status)

        if task_status == "completed":
            task.completed_at = datetime.now(timezone.utc)

        # Persist structured output + any existing metadata
        structured = result.get("structured_output")
        if structured:
            task.task_metadata = structured
        elif result.get("task_metadata"):
            task.task_metadata = result["task_metadata"]

    except Exception as e:
        task.status = TaskStatus.FAILED
        task.final_output = f"Orchestration error: {str(e)}"
        await log_step(task.id, f"Orchestration error: {str(e)}", level="error")

    await session.flush()
    await log_step(task.id, f"Task #{task.id} finished — status: {task.status.value}")
