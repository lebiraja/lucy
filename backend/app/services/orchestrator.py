"""Lucy Orchestrator Engine — thin adapter over LangGraph.

This module preserves the original execute_task() signature (session, task, agents)
called by routers/tasks.py. All orchestration logic has been migrated to the
LangGraph engine in services/langgraph/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Task, TaskStatus
from app.services.langgraph.executor import graph_executor
from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.utility_nodes import log_step


async def execute_task(session: AsyncSession, task: Task, agents: list[Agent]) -> None:
    """Main entry point — dispatch to LangGraph graph executor.

    This preserves the exact same signature as the original orchestrator
    so that routers/tasks.py::_run_task_background() requires zero changes.

    Args:
        session: The caller's DB session (used for final task update only).
        task: The Task ORM object to execute.
        agents: List of Agent ORM objects to participate.
    """
    task.status = TaskStatus.RUNNING
    await session.flush()

    await log_step(task.id, f"Task #{task.id} started — strategy: {task.strategy.value}")

    try:
        # Serialize agents to dicts for LangGraph state transport
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

        # Build initial state
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
            "project_plan": None,
            "agent_allocation": None,
            "task_breakdown": [],
            "manager_checklists": {},
            "hierarchy_results": [],
            "rework_count": 0,
            "final_output": None,
            "task_status": "running",
            "error": None,
        }

        # Execute graph
        result = await graph_executor.run(initial_state)

        # Write results back to task ORM object
        task.final_output = result.get("final_output")
        task_status = result.get("task_status", "completed")
        task.status = TaskStatus(task_status)

        if task_status == "completed":
            task.completed_at = datetime.now(timezone.utc)

        # Council metadata is persisted by the council graph itself,
        # but for non-council strategies, ensure task_metadata from
        # the graph result is captured if present
        if result.get("task_metadata"):
            task.task_metadata = result["task_metadata"]

    except Exception as e:
        task.status = TaskStatus.FAILED
        task.final_output = f"Orchestration error: {str(e)}"
        await log_step(task.id, f"Orchestration error: {str(e)}", level="error")

    await session.flush()
    await log_step(task.id, f"Task #{task.id} finished — status: {task.status.value}")
