"""SQLAlchemy ORM models for Lucy."""

import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ---------- Enums ----------

class AgentRole(str, enum.Enum):
    CEO = "ceo"
    CTO = "cto"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class OperationalStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class InfrastructureStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class AgentState(str, enum.Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    PLANNING = "planning"
    DELEGATING = "delegating"
    EXECUTING = "executing"
    WAITING = "waiting"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class TaskStrategy(str, enum.Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DYNAMIC = "dynamic"
    COUNCIL = "council"
    HIERARCHICAL = "hierarchical"  # CEO-led hierarchical workflow


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LogLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"
    AGENT = "agent"


class ProjectStatus(str, enum.Enum):
    INTAKE = "intake"               # CEO collecting requirements
    PLANNING = "planning"           # Level 0.5 agents designing architecture
    PLANNING_REVIEW = "planning_review"  # CEO reviewing plan
    TECHNICAL_STRATEGY = "technical_strategy"  # CTO breaking into modules
    IN_PROGRESS = "in_progress"     # Managers + Workers executing
    MONITORING = "monitoring"       # Active monitoring phase
    COMPLETED = "completed"
    FAILED = "failed"
    ON_HOLD = "on_hold"             # Paused (e.g. waiting for agents)


class PlanningSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    REJECTED = "rejected"           # CEO rejected plan, needs re-plan
    DEACTIVATED = "deactivated"     # Planning agents shut down


class ModuleStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageType(str, enum.Enum):
    TASK_ASSIGNMENT = "task_assignment"
    STATUS_REPORT = "status_report"
    CLARIFICATION = "clarification"
    PROGRESS_UPDATE = "progress_update"
    ESCALATION = "escalation"
    ADMIN_ALERT = "admin_alert"     # CEO warning admin about insufficient agents
    DELEGATION = "delegation"
    COMPLETION = "completion"


class MessagePriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ---------- Models ----------

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    endpoint = Column(String(512), nullable=False)  # e.g. http://192.168.73.41:9002
    model_name = Column(String(255), nullable=True)  # auto-detected from endpoint
    description = Column(Text, nullable=True)

    # Hierarchical role system
    role = Column(Enum(AgentRole), default=AgentRole.EMPLOYEE, nullable=False)
    parent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # Status tracking
    operational_status = Column(
        Enum(OperationalStatus), default=OperationalStatus.ACTIVE, nullable=False
    )
    infrastructure_status = Column(
        Enum(InfrastructureStatus), default=InfrastructureStatus.OFFLINE, nullable=False
    )
    state = Column(Enum(AgentState), default=AgentState.IDLE, nullable=False)

    # Orchestrator flag
    is_orchestrator = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Per-agent model parameters
    temperature = Column(Float, default=0.7, nullable=False)
    max_tokens = Column(Integer, default=512, nullable=False)
    top_p = Column(Float, default=0.95, nullable=False)
    context_window_tokens = Column(Integer, default=4096, nullable=False)

    # Execution limits
    max_iterations = Column(Integer, default=10, nullable=False)
    timeout_seconds = Column(Integer, default=300, nullable=False)

    # Runtime metrics
    crash_count = Column(Integer, default=0, nullable=False)
    avg_response_time_ms = Column(Float, nullable=True)
    is_warm = Column(Boolean, default=False, nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    last_checkpoint = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    task_steps = relationship("TaskStep", back_populates="agent")
    children = relationship("Agent", back_populates="parent", foreign_keys=[parent_id])
    parent = relationship("Agent", back_populates="children", remote_side=[id])
    sent_messages = relationship("AgentMessage", back_populates="sender", foreign_keys="AgentMessage.sender_id")
    received_messages = relationship("AgentMessage", back_populates="receiver", foreign_keys="AgentMessage.receiver_id")
    checklists = relationship("Checklist", back_populates="agent")
    audit_logs = relationship("AuditLog", back_populates="agent")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt = Column(Text, nullable=False)
    strategy = Column(Enum(TaskStrategy), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    final_output = Column(Text, nullable=True)
    task_metadata = Column(JSON, nullable=True)  # renamed from metadata to avoid SQLAlchemy conflicts

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    steps = relationship("TaskStep", back_populates="task", order_by="TaskStep.step_order")
    logs = relationship("LogEntry", back_populates="task", order_by="LogEntry.timestamp")
    project = relationship("Project", back_populates="tasks")
    checklists = relationship("Checklist", back_populates="task")


class TaskStep(Base):
    __tablename__ = "task_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    step_order = Column(Integer, nullable=False, default=0)
    input_prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(Enum(StepStatus), default=StepStatus.PENDING, nullable=False)
    step_label = Column(String(50), nullable=True)  # "opinion", "review", "synthesis"
    step_metadata = Column(JSON, nullable=True)  # Store checkpoints and recovery data

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", back_populates="steps")
    agent = relationship("Agent", back_populates="task_steps")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    level = Column(Enum(LogLevel), default=LogLevel.INFO, nullable=False)
    source = Column(String(255), nullable=False, default="system")
    message = Column(Text, nullable=False)

    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", back_populates="logs")


# ---------- Project & Hierarchical Workflow Models ----------

class Project(Base):
    """Client project — the top-level entity for hierarchical orchestration."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    client_requirements = Column(Text, nullable=False)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.INTAKE, nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    estimated_complexity = Column(Integer, nullable=True)  # 1-10 scale

    # CEO who owns this project
    ceo_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # Workforce estimate from planning phase
    required_agents = Column(JSON, nullable=True)  # {"cto": 1, "manager": 3, "employee": 8}
    
    # Strategy and metadata
    task_metadata = Column(JSON, nullable=True)  # Strategy, priority, notes

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    ceo_agent = relationship("Agent", foreign_keys=[ceo_agent_id])
    modules = relationship("ProjectModule", back_populates="project", order_by="ProjectModule.id")
    planning_sessions = relationship("PlanningSession", back_populates="project")
    tasks = relationship("Task", back_populates="project")
    messages = relationship("AgentMessage", back_populates="project")


class ProjectModule(Base):
    """Technical module within a project — created by CTO, assigned to managers."""
    __tablename__ = "project_modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # e.g. "Frontend System", "Backend APIs"
    description = Column(Text, nullable=True)
    technology = Column(String(255), nullable=True)  # e.g. "React", "FastAPI"
    complexity = Column(Integer, default=5, nullable=False)  # 1-10 scale
    status = Column(Enum(ModuleStatus), default=ModuleStatus.PENDING, nullable=False)

    # Manager who owns this module
    assigned_manager_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="modules")
    assigned_manager = relationship("Agent", foreign_keys=[assigned_manager_id])


class PlanningSession(Base):
    """Level 0.5 planning session — temporary agents design architecture."""
    __tablename__ = "planning_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status = Column(
        Enum(PlanningSessionStatus), default=PlanningSessionStatus.ACTIVE, nullable=False
    )

    # Planning outputs (stored as JSON)
    architecture = Column(JSON, nullable=True)       # System architecture proposal
    module_breakdown = Column(JSON, nullable=True)   # Proposed modules
    tech_stack = Column(JSON, nullable=True)          # Technology recommendations
    workforce_estimate = Column(JSON, nullable=True)  # How many agents needed per role
    risk_analysis = Column(JSON, nullable=True)       # Identified risks
    execution_plan = Column(JSON, nullable=True)      # Phased execution plan

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="planning_sessions")


class Checklist(Base):
    """Connected checklist items — every agent maintains per-task checklists."""
    __tablename__ = "checklists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    # Linked parent for roll-up (Employee → Manager → CTO → CEO)
    parent_checklist_id = Column(
        Integer, ForeignKey("checklists.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", back_populates="checklists")
    agent = relationship("Agent", back_populates="checklists")
    children = relationship("Checklist", back_populates="parent_checklist",
                            foreign_keys=[parent_checklist_id])
    parent_checklist = relationship("Checklist", back_populates="children",
                                    remote_side=[id])


class AgentMessage(Base):
    """Hierarchical communication — enforces chain of command."""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    receiver_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)

    message_type = Column(Enum(MessageType), nullable=False)
    payload = Column(JSON, nullable=False)  # JSONB content
    priority = Column(Enum(MessagePriority), default=MessagePriority.NORMAL, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)

    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    sender = relationship("Agent", back_populates="sent_messages", foreign_keys=[sender_id])
    receiver = relationship("Agent", back_populates="received_messages", foreign_keys=[receiver_id])
    project = relationship("Project", back_populates="messages")


class AuditLog(Base):
    """Audit trail for all agent actions."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(100), nullable=False)  # e.g. "agent_created", "task_assigned"
    entity_type = Column(String(100), nullable=True)    # e.g. "project", "task", "agent"
    entity_id = Column(Integer, nullable=True)
    task_metadata = Column(JSON, nullable=True)

    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    agent = relationship("Agent", back_populates="audit_logs")


class TaskChatMessage(Base):
    """Chat messages on task pages - for agent and system communication."""
    __tablename__ = "task_chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    message = Column(Text, nullable=False)
    message_type = Column(String(50), default="chat", nullable=False)  # chat, system, notification
    
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", back_populates="chat_messages")
    sender = relationship("Agent", back_populates="chat_messages")


# Add back-populates to Task and Agent models
Task.chat_messages = relationship("TaskChatMessage", back_populates="task", order_by="TaskChatMessage.created_at")
Agent.chat_messages = relationship("TaskChatMessage", back_populates="sender")
