"""Task creation and execution API routes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models import Agent, Task, TaskStatus
from app.schemas import TaskCreate, TaskResponse
from app.services.orchestrator import execute_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


async def _run_task_background(task_id: int, agent_ids: list[int] | None):
    """Background coroutine to execute a task outside the request lifecycle."""
    async with async_session() as session:
        try:
            task = await session.get(Task, task_id)
            if not task:
                return

            # Get agents
            if agent_ids:
                result = await session.execute(
                    select(Agent).where(Agent.id.in_(agent_ids), Agent.is_active == True)
                )
            else:
                result = await session.execute(
                    select(Agent).where(Agent.is_active == True)
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
            # Try to mark as failed
            try:
                task = await session.get(Task, task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.final_output = f"Fatal error: {str(e)}"
                    await session.commit()
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
    await db.flush()
    await db.refresh(task)

    # Launch execution in background
    asyncio.create_task(_run_task_background(task.id, data.agent_ids))

    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all tasks with their steps."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps))
        .order_by(Task.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    tasks = result.scalars().unique().all()

    # Enrich steps with agent names
    response_tasks = []
    for task in tasks:
        task_dict = TaskResponse.model_validate(task)
        for step_resp in task_dict.steps:
            if step_resp.agent_id:
                agent = await db.get(Agent, step_resp.agent_id)
                step_resp.agent_name = agent.name if agent else None
        response_tasks.append(task_dict)

    return response_tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific task with all steps."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_resp = TaskResponse.model_validate(task)
    for step_resp in task_resp.steps:
        if step_resp.agent_id:
            agent = await db.get(Agent, step_resp.agent_id)
            step_resp.agent_name = agent.name if agent else None

    return task_resp
