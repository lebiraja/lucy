"""
Phase 1 Tests — Database models, schemas, agent registry.
Uses mostly SQLite in-memory engine to prevent DB clashes locally.
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base, Agent, AgentRole, OperationalStatus, InfrastructureStatus, AgentState,
    Project, ProjectStatus, ProjectModule, ModuleStatus,
    PlanningSession, PlanningSessionStatus,
    Checklist, AgentMessage, MessageType, MessagePriority,
    AuditLog, TaskStrategy,
)
from app.schemas import (
    ProjectCreate, AgentFleetStatus, AgentRoleCount,
    AgentRegister, AgentMessageCreate,
)


@pytest.fixture
def sync_engine():
    """Create an in-memory SQLite engine for sync tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    """Create a sync session for model tests."""
    SessionLocal = sessionmaker(bind=sync_engine)
    session = SessionLocal()
    yield session
    session.close()


def test_agent_roles():
    assert AgentRole.CEO.value == "ceo"
    assert AgentRole.CTO.value == "cto"
    assert AgentRole.MANAGER.value == "manager"
    assert AgentRole.EMPLOYEE.value == "employee"


def test_project_model(sync_session):
    project = Project(
        title="Test Project",
        client_requirements="Test requirements",
        status=ProjectStatus.INTAKE,
    )
    sync_session.add(project)
    sync_session.commit()

    assert project.id is not None
    assert project.title == "Test Project"
    assert project.status == ProjectStatus.INTAKE
    assert project.required_agents is None

    # Status transition
    project.status = ProjectStatus.PLANNING
    sync_session.commit()
    assert project.status == ProjectStatus.PLANNING


def test_schema_validation():
    data = ProjectCreate(
        title="System",
        client_requirements="Reqs",
    )
    assert data.title == "System"

    msg = AgentMessageCreate(
        message_type=MessageType.ADMIN_ALERT,
        payload={"msg": "alert"},
        priority=MessagePriority.CRITICAL,
    )
    assert msg.priority == MessagePriority.CRITICAL


def test_fleet_status_logic(sync_session):
    """Verify agent classification into ready/under_review/offline."""
    ready = Agent(
        name="Ready-1", endpoint="http://10.0.0.1:9001",
        role=AgentRole.EMPLOYEE,
        operational_status=OperationalStatus.ACTIVE,
        infrastructure_status=InfrastructureStatus.ONLINE,
        state=AgentState.IDLE,
    )
    paused = Agent(
        name="Review-1", endpoint="http://10.0.0.2:9001",
        role=AgentRole.MANAGER,
        operational_status=OperationalStatus.PAUSED,
        infrastructure_status=InfrastructureStatus.ONLINE,
        state=AgentState.STOPPED,
    )
    busy = Agent(
        name="Busy-1", endpoint="http://10.0.0.3:9001",
        role=AgentRole.EMPLOYEE,
        operational_status=OperationalStatus.ACTIVE,
        infrastructure_status=InfrastructureStatus.ONLINE,
        state=AgentState.EXECUTING,
    )
    offline = Agent(
        name="Offline-1", endpoint="http://10.0.0.4:9001",
        role=AgentRole.CTO,
        operational_status=OperationalStatus.ACTIVE,
        infrastructure_status=InfrastructureStatus.OFFLINE,
        state=AgentState.IDLE,
    )
    sync_session.add_all([ready, paused, busy, offline])
    sync_session.commit()

    agents = sync_session.query(Agent).all()
    ready_count = 0
    review_count = 0
    offline_count = 0

    for a in agents:
        if (
            a.operational_status == OperationalStatus.ACTIVE
            and a.infrastructure_status == InfrastructureStatus.ONLINE
            and a.state in (AgentState.IDLE, AgentState.COMPLETED)
        ):
            ready_count += 1
        elif (
            a.operational_status == OperationalStatus.PAUSED
            or a.state in (AgentState.ASSIGNED, AgentState.PLANNING, AgentState.EXECUTING)
        ):
            review_count += 1
        else:
            offline_count += 1

    assert ready_count == 1
    assert review_count == 2
    assert offline_count == 1
