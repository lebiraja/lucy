"""Agent execution nodes — the core workhorses of the LangGraph engine.

Direct port of orchestrator._run_step() and council-stage-specific prompts.
All DB writes use isolated sessions to support asyncio.gather() concurrency.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.database import async_session
from app.models import Agent, AgentState, TaskStep, StepStatus
from app.services.llm_client import chat_completion
from app.services.langgraph.state import TaskState, AgentResult
from app.services.langgraph.nodes.utility_nodes import log_step


# ---------- Role-aware system prompts (moved from orchestrator.py) ----------

ROLE_SYSTEM_PROMPTS = {
    "ceo": (
        "You are a CEO-level strategic AI. Analyze from a high-level business and strategic perspective. "
        "Focus on vision, priorities, risks, resource allocation, and overall direction."
    ),
    "cto": (
        "You are a CTO-level technical AI. Analyze from a deep technical perspective. "
        "Focus on architecture, technology choices, scalability, security, and engineering trade-offs."
    ),
    "manager": (
        "You are a Manager-level AI responsible for execution. Analyze from an implementation perspective. "
        "Focus on timelines, team capacity, milestones, dependencies, and practical execution steps."
    ),
    "employee": (
        "You are a specialist AI contributor. Provide detailed, hands-on analysis. "
        "Focus on specifics, implementation details, and ground-level insights."
    ),
}


# ---------- Core agent step runner ----------

async def run_agent_step(
    task_id: int,
    agent_dict: dict,
    prompt: str,
    step_order: int,
    step_label: str | None = None,
) -> AgentResult:
    """Execute a single agent step — direct port of orchestrator._run_step().

    Uses an isolated DB session for safe concurrent execution.
    Creates a TaskStep record, calls chat_completion(), updates agent metrics.
    """
    async with async_session() as session:
        agent = await session.get(Agent, agent_dict["id"])
        if not agent:
            return AgentResult(
                agent_id=agent_dict["id"],
                agent_name=agent_dict.get("name", "unknown"),
                agent_role=agent_dict.get("role", "employee"),
                model_name="unknown",
                response="Agent not found in database",
                duration_ms=0,
                status="failed",
                step_label=step_label,
            )

        step = TaskStep(
            task_id=task_id,
            agent_id=agent.id,
            step_order=step_order,
            input_prompt=prompt,
            status=StepStatus.RUNNING,
            step_label=step_label,
        )
        session.add(step)

        # Mark agent as executing
        agent.state = AgentState.EXECUTING
        agent.last_heartbeat = datetime.now(timezone.utc)
        await session.commit()

        await log_step(
            task_id,
            f"Sending prompt to [{agent.name}] ({agent.model_name or 'auto'})...",
            source=agent.name,
        )

        try:
            await session.refresh(step)
            response_text, duration_ms = await chat_completion(
                agent=agent,
                messages=[{"role": "user", "content": prompt}],
            )

            step.response = response_text
            step.duration_ms = duration_ms
            step.status = StepStatus.COMPLETED

            # Update agent metrics (EMA of response time)
            agent.state = AgentState.IDLE
            if agent.avg_response_time_ms is not None:
                agent.avg_response_time_ms = round(
                    agent.avg_response_time_ms * 0.8 + duration_ms * 0.2, 1
                )
            else:
                agent.avg_response_time_ms = float(duration_ms)

            await session.commit()

            await log_step(
                task_id,
                f"[{agent.name}] responded in {duration_ms}ms ({len(response_text)} chars)",
                source=agent.name,
                level="agent",
            )
            return AgentResult(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_role=agent.role.value,
                model_name=agent.model_name or "unknown",
                response=response_text,
                duration_ms=duration_ms,
                status="completed",
                step_label=step_label,
            )

        except Exception as e:
            step.status = StepStatus.FAILED
            step.response = f"ERROR: {str(e)}"

            agent.state = AgentState.FAILED
            agent.crash_count = (agent.crash_count or 0) + 1
            await session.commit()

            await log_step(
                task_id,
                f"[{agent.name}] FAILED: {str(e)}",
                source=agent.name,
                level="error",
            )
            return AgentResult(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_role=agent.role.value,
                model_name=agent.model_name or "unknown",
                response=f"ERROR: {str(e)}",
                duration_ms=0,
                status="failed",
                step_label=step_label,
            )
