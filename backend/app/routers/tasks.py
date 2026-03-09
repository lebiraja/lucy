"""Task creation and execution API routes."""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models import Agent, Task, TaskStatus, LogEntry, TaskStep, OperationalStatus
from app.schemas import TaskCreate, TaskResponse, LogEntryResponse
from app.services.orchestrator import execute_task
from app.services.logger import log_broadcaster

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Hold references to background tasks to prevent GC cancellation
_background_tasks: set[asyncio.Task] = set()


def _enrich_steps(task_resp: TaskResponse, steps_with_agents: list) -> None:
    """Populate agent_name and agent_role on step responses without extra DB queries."""
    agent_map = {s.id: s.agent for s in steps_with_agents if s.agent}
    for step_resp in task_resp.steps:
        agent = agent_map.get(step_resp.id)
        if agent:
            step_resp.agent_name = agent.name
            step_resp.agent_role = agent.role.value


async def _run_task_background(task_id: int, agent_ids: list[int] | None):
    """Background coroutine to execute a task outside the request lifecycle."""
    async with async_session() as session:
        try:
            task = await session.get(Task, task_id)
            if not task:
                return

            if agent_ids:
                result = await session.execute(
                    select(Agent).where(
                        Agent.id.in_(agent_ids),
                        Agent.is_active == True,
                        Agent.operational_status == OperationalStatus.ACTIVE,
                    )
                )
            else:
                result = await session.execute(
                    select(Agent).where(
                        Agent.is_active == True,
                        Agent.operational_status == OperationalStatus.ACTIVE,
                    )
                )
            agents = list(result.scalars().all())

            if not agents:
                task.status = TaskStatus.FAILED
                task.final_output = "No active agents available."
                await session.commit()
                return

            await execute_task(session, task, agents)
            await session.commit()
        except Exception as e:
            await session.rollback()
            try:
                async with async_session() as recovery_session:
                    task = await recovery_session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.FAILED
                        task.final_output = f"Fatal error: {str(e)}"
                        await recovery_session.commit()
            except Exception:
                pass


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create and execute a new orchestration task."""
    task = Task(
        prompt=data.prompt,
        strategy=data.strategy,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    await db.commit()

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps))
        .where(Task.id == task.id)
    )
    task = result.scalar_one()

    # Keep reference to prevent GC from canceling the running task
    bg_task = asyncio.create_task(_run_task_background(task.id, data.agent_ids))
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_background_tasks.discard)

    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all tasks with their steps (agents eagerly loaded — no N+1)."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps).joinedload(TaskStep.agent))
        .order_by(Task.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    tasks = result.scalars().unique().all()

    response_tasks = []
    for task in tasks:
        task_resp = TaskResponse.model_validate(task)
        for step_resp in task_resp.steps:
            # Find the ORM step to access its eagerly-loaded agent
            orm_step = next((s for s in task.steps if s.id == step_resp.id), None)
            if orm_step and orm_step.agent:
                step_resp.agent_name = orm_step.agent.name
                step_resp.agent_role = orm_step.agent.role.value
        response_tasks.append(task_resp)

    return response_tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific task with all steps (agents eagerly loaded — no N+1)."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps).joinedload(TaskStep.agent))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_resp = TaskResponse.model_validate(task)
    for step_resp in task_resp.steps:
        orm_step = next((s for s in task.steps if s.id == step_resp.id), None)
        if orm_step and orm_step.agent:
            step_resp.agent_name = orm_step.agent.name
            step_resp.agent_role = orm_step.agent.role.value

    return task_resp


@router.get("/{task_id}/logs", response_model=list[LogEntryResponse])
async def get_task_logs(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get all logs for a specific task."""
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.task_id == task_id)
        .order_by(LogEntry.timestamp.asc())
    )
    return result.scalars().all()


@router.get("/{task_id}/events")
async def stream_task_events(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Server-Sent Events stream for a task. Yields log messages in real time,
    then sends a final 'done' event when the task completes or fails."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        # If task already finished, send done immediately
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            payload = json.dumps({"type": "done", "status": task.status.value, "task_id": task_id})
            yield f"data: {payload}\n\n"
            return

        queue = log_broadcaster.subscribe(task_id=task_id)
        try:
            while True:
                # Respect client disconnect
                if await request.is_disconnected():
                    break

                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=25)
                    # raw is already a JSON string from broadcast()
                    yield f"data: {raw}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat + check for task completion
                    yield ": heartbeat\n\n"
                    async with async_session() as s:
                        t = await s.get(Task, task_id)
                        if t and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                            payload = json.dumps({"type": "done", "status": t.status.value, "task_id": task_id})
                            yield f"data: {payload}\n\n"
                            break
        finally:
            log_broadcaster.unsubscribe(queue, task_id=task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
