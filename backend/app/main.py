"""Lucy — Multi-Agent Orchestration Platform Backend."""

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import engine, get_db
from app.models import Base, Task, TaskStatus
from app.routers import agents, tasks, ws

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB tables + shared httpx client. Shutdown: clean up."""
    import time
    app.state.start_time = time.time()

    # Shared HTTP client for all vLLM calls — enables connection pooling
    import app.services.llm_client as llm_client
    llm_client._http_client = httpx.AsyncClient(
        timeout=settings.llm_request_timeout,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Reset tasks left in-flight from a previous crashed/reloaded server run
        await conn.execute(
            sa_update(Task)
            .where(Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]))
            .values(
                status=TaskStatus.FAILED,
                final_output="Server restarted while task was in progress",
            )
        )
    yield

    await llm_client._http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="Lucy — Multi-Agent Orchestrator",
    description="Central orchestration platform for managing and coordinating multiple LLM agents via vLLM.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — use explicit origins from settings (wildcard + credentials is invalid per browser spec)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select, func
    from app.models import Agent, Task, TaskStatus

    total_agents = await db.scalar(select(func.count(Agent.id))) or 0
    online_agents = await db.scalar(
        select(func.count(Agent.id)).where(Agent.infrastructure_status == "online")
    ) or 0

    active_tasks = await db.scalar(
        select(func.count(Task.id)).where(Task.status == TaskStatus.RUNNING)
    ) or 0
    completed_tasks = await db.scalar(
        select(func.count(Task.id)).where(Task.status == TaskStatus.COMPLETED)
    ) or 0
    failed_tasks = await db.scalar(
        select(func.count(Task.id)).where(Task.status == TaskStatus.FAILED)
    ) or 0

    total_finished = completed_tasks + failed_tasks
    success_rate = 100 if total_finished == 0 else int((completed_tasks / total_finished) * 100)
    
    # Calculate simple uptime since the app started
    import time
    if not hasattr(app.state, "start_time"):
        app.state.start_time = time.time()
    uptime_seconds = int(time.time() - app.state.start_time)

    return {
        "status": "ok",
        "service": "lucy-orchestrator",
        "total_agents": total_agents,
        "online_agents": online_agents,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "success_rate": success_rate,
        "uptime_seconds": uptime_seconds,
    }


@app.get("/api/logs")
async def get_all_logs(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models import LogEntry
    result = await db.execute(
        select(LogEntry).order_by(LogEntry.timestamp.desc()).limit(limit).offset(offset)
    )
    logs = result.scalars().all()
    # Reverse to return oldest to newest in the chunk
    return list(reversed(logs))
