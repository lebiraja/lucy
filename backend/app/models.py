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
    max_tokens = Column(Integer, default=2048, nullable=False)
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


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt = Column(Text, nullable=False)
    strategy = Column(Enum(TaskStrategy), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    final_output = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)  # council rankings, label map, stage data

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    steps = relationship("TaskStep", back_populates="task", order_by="TaskStep.step_order")
    logs = relationship("LogEntry", back_populates="task", order_by="LogEntry.timestamp")


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
