"""Lucy — Multi-Agent Orchestration Platform Backend."""

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine
from app.models import Base
from app.routers import agents, tasks, ws

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB tables + shared httpx client. Shutdown: clean up."""
    # Shared HTTP client for all vLLM calls — enables connection pooling
    import app.services.llm_client as llm_client
    llm_client._http_client = httpx.AsyncClient(
        timeout=settings.llm_request_timeout,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
async def health():
    return {"status": "ok", "service": "lucy-orchestrator"}
