"""Pydantic schemas for request/response serialization."""

from datetime import datetime
from pydantic import BaseModel, Field
from app.models import (
    TaskStrategy, TaskStatus, StepStatus, LogLevel,
    AgentRole, OperationalStatus, InfrastructureStatus, AgentState,
    ProjectStatus, PlanningSessionStatus, ModuleStatus,
    MessageType, MessagePriority,
)


# ---------- Agent Schemas ----------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    endpoint: str = Field(..., min_length=1, max_length=512)
    model_name: str | None = Field(default=None, max_length=255)
    role: AgentRole = AgentRole.EMPLOYEE
    parent_id: int | None = None
    description: str | None = None
    is_active: bool = True
    is_orchestrator: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=128000)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    context_window_tokens: int = Field(default=4096, ge=512, le=1000000)
    max_iterations: int = Field(default=10, ge=1, le=1000)
    timeout_seconds: int = Field(default=300, ge=10, le=86400)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    model_name: str | None = Field(default=None, max_length=255)
    role: AgentRole | None = None
    parent_id: int | None = None
    description: str | None = None
    is_active: bool | None = None
    is_orchestrator: bool | None = None
    operational_status: OperationalStatus | None = None
    state: AgentState | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    context_window_tokens: int | None = Field(default=None, ge=512, le=1000000)
    max_iterations: int | None = Field(default=None, ge=1, le=1000)
    timeout_seconds: int | None = Field(default=None, ge=10, le=86400)


class AgentResponse(BaseModel):
    id: int
    name: str
    endpoint: str
    model_name: str | None
    role: AgentRole
    parent_id: int | None
    description: str | None
    is_active: bool
    is_orchestrator: bool
    operational_status: OperationalStatus
    infrastructure_status: InfrastructureStatus
    state: AgentState
    temperature: float
    max_tokens: int
    top_p: float
    context_window_tokens: int
    max_iterations: int
    timeout_seconds: int
    crash_count: int
    avg_response_time_ms: float | None
    is_warm: bool
    last_heartbeat: datetime | None
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
    project_id: int | None = None
    final_output: str | None
    task_metadata: dict | None = None
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
    step_label: str | None = None
    created_at: datetime
    agent_name: str | None = None
    agent_role: str | None = None

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


# ---------- Project Schemas ----------

class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    client_requirements: str = Field(..., min_length=1)
    deadline: datetime | None = None


class ProjectResponse(BaseModel):
    id: int
    title: str
    client_requirements: str
    status: ProjectStatus
    deadline: datetime | None
    estimated_complexity: int | None
    ceo_agent_id: int | None
    required_agents: dict | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ProjectModuleResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None
    technology: str | None
    complexity: int
    status: ModuleStatus
    assigned_manager_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanningSessionResponse(BaseModel):
    id: int
    project_id: int
    status: PlanningSessionStatus
    architecture: dict | None
    module_breakdown: dict | None
    tech_stack: dict | None
    workforce_estimate: dict | None
    risk_analysis: dict | None
    execution_plan: dict | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- Checklist Schemas ----------

class ChecklistCreate(BaseModel):
    task_id: int
    agent_id: int | None = None
    title: str = Field(..., min_length=1, max_length=500)
    order_index: int = 0
    parent_checklist_id: int | None = None


class ChecklistResponse(BaseModel):
    id: int
    task_id: int
    agent_id: int | None
    title: str
    completed: bool
    order_index: int
    parent_checklist_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Agent Message Schemas ----------

class AgentMessageCreate(BaseModel):
    sender_id: int | None = None
    receiver_id: int | None = None
    project_id: int | None = None
    task_id: int | None = None
    message_type: MessageType
    payload: dict
    priority: MessagePriority = MessagePriority.NORMAL


class AgentMessageResponse(BaseModel):
    id: int
    sender_id: int | None
    receiver_id: int | None
    project_id: int | None
    task_id: int | None
    message_type: MessageType
    payload: dict
    priority: MessagePriority
    is_read: bool
    timestamp: datetime

    model_config = {"from_attributes": True}


# ---------- Audit Log Schemas ----------

class AuditLogResponse(BaseModel):
    id: int
    agent_id: int | None
    action_type: str
    entity_type: str | None
    entity_id: int | None
    task_metadata: dict | None
    timestamp: datetime

    model_config = {"from_attributes": True}


# ---------- Fleet Status Schemas (CEO Awareness) ----------

class AgentRoleCount(BaseModel):
    """Count of agents for a specific role."""
    role: AgentRole
    ready: int = 0
    under_review: int = 0
    offline: int = 0
    total: int = 0


class AgentFleetStatus(BaseModel):
    """CEO fleet overview — how many agents are in each state."""
    total_agents: int
    ready_count: int        # ACTIVE + ONLINE
    under_review_count: int  # PAUSED or ASSIGNED/PLANNING state
    offline_count: int       # OFFLINE or STOPPED/FAILED
    by_role: list[AgentRoleCount]
    insufficient_roles: list[str] = []  # roles where demand > supply


class AgentRegister(BaseModel):
    """Self-registration payload from an agent joining the network."""
    name: str = Field(..., min_length=1, max_length=255)
    endpoint: str = Field(..., min_length=1, max_length=512)
    role: AgentRole = AgentRole.EMPLOYEE
    description: str | None = None


# ---------- Bulk Registration & Retrain Schemas ----------

class BulkRegisterItem(BaseModel):
    """Single agent in a bulk registration request."""
    name: str = Field(..., min_length=1, max_length=255)
    endpoint: str = Field(..., min_length=1, max_length=512)
    description: str | None = None


class BulkRegisterRequest(BaseModel):
    """Bulk registration — CEO registers all agents as generic workers."""
    agents: list[BulkRegisterItem] = Field(..., min_length=1)


class BulkRegisterResult(BaseModel):
    """Result for a single agent in bulk registration."""
    name: str
    endpoint: str
    success: bool
    agent_id: int | None = None
    model_name: str | None = None
    error: str | None = None


class BulkRegisterResponse(BaseModel):
    """Response for bulk registration."""
    registered: int
    failed: int
    results: list[BulkRegisterResult]


class AgentRetrainRequest(BaseModel):
    """CEO retrains an agent — assigns role, updates config, feeds context."""
    role: AgentRole
    parent_id: int | None = None
    description: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    system_context: str | None = None  # CEO-provided context for the agent


# ---------- Agent Assignment & Strategy Schemas ----------

class ProjectStrategy(BaseModel):
    """Strategy selection for a project by CEO."""
    strategy_type: TaskStrategy = TaskStrategy.HIERARCHICAL
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    estimated_duration_days: int | None = None
    notes: str | None = None


class AgentAssignment(BaseModel):
    """Manual agent assignment to a project."""
    agent_id: int
    role_on_project: str | None = None  # Optional override role


class AgentAssignmentRequest(BaseModel):
    """Request to assign multiple agents to a project."""
    project_id: int
    agents: list[AgentAssignment]
    strategy: ProjectStrategy | None = None


class AgentAssignmentResult(BaseModel):
    """Result of agent assignment."""
    project_id: int
    assigned_agents: list[dict]
    unassigned_agents: list[dict]
    warnings: list[str] = []
    auto_assigned: bool = False


class AvailabilityNotification(BaseModel):
    """Notification about agent availability."""
    notification_type: str  # "insufficient_agents", "agents_available", "auto_assigned"
    project_id: int
    project_title: str
    message: str
    available_agents: list[dict] = []
    required_roles: dict[str, int] = {}
    timestamp: datetime


class ChatMessageCreate(BaseModel):
    """Create a chat message on a task."""
    task_id: int
    sender_id: int | None = None
    message: str = Field(..., min_length=1, max_length=10000)
    message_type: str = Field(default="chat", pattern="^(chat|system|notification)$")


class ChatMessageResponse(BaseModel):
    """Chat message response."""
    id: int
    task_id: int
    sender_id: int | None
    sender_name: str | None
    sender_role: str | None
    message: str
    message_type: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ---------- Fleet Summary Schemas (CEO Deep Awareness) ----------

class FleetAgentDetail(BaseModel):
    """Individual agent detail within fleet summary."""
    id: int
    name: str
    role: AgentRole
    state: AgentState
    operational_status: OperationalStatus
    infrastructure_status: InfrastructureStatus
    model_name: str | None = None
    is_warm: bool = False

    model_config = {"from_attributes": True}


class FleetRoleDetail(BaseModel):
    """Per-role breakdown with individual agent details."""
    role: AgentRole
    ready: int = 0
    busy: int = 0
    offline: int = 0
    total: int = 0
    agents: list[FleetAgentDetail] = []


class WorkforceDemand(BaseModel):
    """Demand from a single active project."""
    project_id: int
    project_title: str
    required: dict[str, int] = {}  # {"cto": 1, "manager": 3, "employee": 8}


class FleetSummaryResponse(BaseModel):
    """CEO fleet summary — deep awareness of all agents and workforce needs."""
    total_agents: int
    ready_count: int
    busy_count: int
    offline_count: int
    by_role: list[FleetRoleDetail]
    workforce_demand: list[WorkforceDemand] = []
    insufficient_roles: list[str] = []
    unassigned_count: int = 0  # employees not yet assigned to higher roles

