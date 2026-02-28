"""Lucy — Multi-Agent Orchestration Platform Backend."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.models import Base
from app.routers import agents, tasks, ws

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Lucy — Multi-Agent Orchestrator",
    description="Central orchestration platform for managing and coordinating multiple LLM agents via vLLM.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "lucy-orchestrator"}
