"""Project orchestration router for hierarchical multi-agent teams."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from app.database import get_db, async_session
from app.models import Project, ProjectStatus, Task, TaskStrategy, TaskStatus
from app.schemas import ProjectCreate, ProjectResponse, TaskResponse
from app.services.orchestrator import execute_task

router = APIRouter(prefix="/api/projects", tags=["projects"])

_background_projects: set[asyncio.Task] = set()

async def _run_project_background(project_id: int):
    async with async_session() as session:
        try:
            project = await session.get(Project, project_id)
            if not project:
                return
                
            project.status = ProjectStatus.ACTIVE
            
            # Create a top-level hierarchical task
            task = Task(
                project_id=project.id,
                prompt=project.description,
                strategy=TaskStrategy.HIERARCHICAL,
                status=TaskStatus.PENDING,
            )
            session.add(task)
            await session.commit()
            
            # Get all active agents for the hierarchical graph
            from app.models import Agent, OperationalStatus
            result = await session.execute(
                select(Agent).where(
                    Agent.is_active == True,
                    Agent.operational_status == OperationalStatus.ACTIVE,
                )
            )
            agents = list(result.scalars().all())
            
            if not agents:
                task.status = TaskStatus.FAILED
                task.final_output = "No active agents available for project execution."
                project.status = ProjectStatus.FAILED
                await session.commit()
                return
                
            await execute_task(session, task, agents)
            
            # Update project from task
            from datetime import datetime, timezone
            
            if task.status == TaskStatus.COMPLETED:
                project.status = ProjectStatus.COMPLETED
                project.completed_at = datetime.now(timezone.utc)
            elif task.status == TaskStatus.FAILED:
                project.status = ProjectStatus.FAILED
            
            if task.task_metadata:
                project.plan = task.task_metadata.get("project_plan")
                project.agent_allocation = task.task_metadata.get("agent_allocation")
                
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            try:
                async with async_session() as recovery:
                    p = await recovery.get(Project, project_id)
                    if p:
                        p.status = ProjectStatus.FAILED
                        await recovery.commit()
            except Exception:
                pass


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=data.name,
        description=data.description,
        status=ProjectStatus.PENDING,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.tasks))
        .order_by(Project.created_at.desc())
    )
    return result.scalars().unique().all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.tasks).selectinload(Task.steps))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/execute", response_model=ProjectResponse)
async def execute_project(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    bg_task = asyncio.create_task(_run_project_background(project.id))
    _background_projects.add(bg_task)
    bg_task.add_done_callback(_background_projects.discard)
    
    return project
