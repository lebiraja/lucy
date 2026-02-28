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
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ---------- Enums ----------

class TaskStrategy(str, enum.Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DYNAMIC = "dynamic"


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
    model_name = Column(String(255), nullable=False)  # e.g. Qwen/Qwen2.5-72B
    role = Column(String(255), nullable=False, default="general")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_orchestrator = Column(Boolean, default=False, nullable=False)

    # Per-agent model parameters
    temperature = Column(Float, default=0.7, nullable=False)
    max_tokens = Column(Integer, default=2048, nullable=False)
    top_p = Column(Float, default=0.95, nullable=False)

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


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt = Column(Text, nullable=False)
    strategy = Column(Enum(TaskStrategy), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    final_output = Column(Text, nullable=True)

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
