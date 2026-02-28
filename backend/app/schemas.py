"""Pydantic schemas for request/response serialization."""

from datetime import datetime
from pydantic import BaseModel, Field
from app.models import TaskStrategy, TaskStatus, StepStatus, LogLevel


# ---------- Agent Schemas ----------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    endpoint: str = Field(..., min_length=1, max_length=512)
    model_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="general", max_length=255)
    description: str | None = None
    is_active: bool = True
    is_orchestrator: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=128000)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    is_orchestrator: bool | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    id: int
    name: str
    endpoint: str
    model_name: str
    role: str
    description: str | None
    is_active: bool
    is_orchestrator: bool
    temperature: float
    max_tokens: int
    top_p: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentHealth(BaseModel):
    id: int
    name: str
    endpoint: str
    is_online: bool
    latency_ms: float | None = None
    error: str | None = None


# ---------- Task Schemas ----------

class TaskCreate(BaseModel):
    prompt: str = Field(..., min_length=1)
    strategy: TaskStrategy
    agent_ids: list[int] | None = None  # None = use all active agents


class TaskResponse(BaseModel):
    id: int
    prompt: str
    strategy: TaskStrategy
    status: TaskStatus
    final_output: str | None
    created_at: datetime
    completed_at: datetime | None
    steps: list["TaskStepResponse"] = []

    model_config = {"from_attributes": True}


class TaskStepResponse(BaseModel):
    id: int
    task_id: int
    agent_id: int | None
    step_order: int
    input_prompt: str
    response: str | None
    duration_ms: int | None
    status: StepStatus
    created_at: datetime
    agent_name: str | None = None

    model_config = {"from_attributes": True}


# ---------- Log Schemas ----------

class LogEntryResponse(BaseModel):
    id: int
    task_id: int | None
    level: LogLevel
    source: str
    message: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogBroadcast(BaseModel):
    """Schema for WebSocket log messages."""
    task_id: int | None = None
    level: str
    source: str
    message: str
    timestamp: str
