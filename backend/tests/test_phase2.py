"""
Phase 2 Tests — Core Engine (LangGraph, AutoGen, Memory, Agents).
Tests the logic of the workflow, communication Wrapper, and specific agent prompting.
"""

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Agent, AgentRole, Task, TaskStrategy, TaskStatus, StepStatus, Project, ProjectStatus

# Import Phase 2 components
from app.services.workflow_engine import create_project_workflow
from app.services.autogen_comm import HierarchicalCommunicator
from app.services.memory import MemoryManager
from app.agents.ceo_agent import CeoAgentManager, CeoAnalysisOutput, CeoReviewOutput
from app.agents.planning_agents import PlanningAgentManager, PlanningOutput, ArchitectureComponent, WorkforceEstimate
from app.agents.cto_agent import CTOAgentManager, CTOStrategyOutput, DerivedModule


@pytest.fixture
def sync_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    SessionLocal = sessionmaker(bind=sync_engine)
    session = SessionLocal()
    yield session
    session.close()


# ==================== Workflow Engine Tests ====================

def test_workflow_engine_compilation():
    """Ensure the LangGraph state machine compiles without errors."""
    workflow = create_project_workflow()
    assert workflow is not None

@pytest.mark.asyncio
async def test_workflow_ceo_review_routing():
    """Test conditional routing logic after CEO review."""
    from app.services.workflow_engine import route_after_ceo_review

    # Approved & sufficient -> go to CTO
    state1 = {
        "planning_approved": True,
        "agents_sufficient": True,
    }
    assert route_after_ceo_review(state1) == "cto_strategy"

    # Not approved -> re-plan
    state2 = {
        "planning_approved": False,
        "agents_sufficient": True,
    }
    assert route_after_ceo_review(state2) == "planning_node"

    # Approved but insufficient -> alert admin
    state3 = {
        "planning_approved": True,
        "agents_sufficient": False,
    }
    assert route_after_ceo_review(state3) == "admin_alert"


@pytest.mark.asyncio
async def test_execute_hierarchical_flow(monkeypatch, sync_session):
    """Test that hierarchical strategy runs through planning/CEO/execution and completes."""
    from app.services.orchestrator import execute_hierarchical

    # Setup test task and agents
    task = Task(prompt="Build secure API", strategy=TaskStrategy.HIERARCHICAL, status=TaskStatus.PENDING)
    sync_session.add(task)
    sync_session.flush()

    ceo = Agent(name="CEO", endpoint="http://localhost:8000", role=AgentRole.CEO, is_orchestrator=True, is_active=True)
    planner = Agent(name="Planner", endpoint="http://localhost:8000", role=AgentRole.MANAGER, is_active=True)
    worker = Agent(name="Worker", endpoint="http://localhost:8000", role=AgentRole.EMPLOYEE, is_active=True)
    sync_session.add_all([ceo, planner, worker])
    sync_session.commit()

    async def fake_run_step(task_id, agent, prompt, step_order, step_label=None):
        return {"status": StepStatus.COMPLETED, "response": f"OK-{agent.name}-{step_label}", "duration_ms": 50}

    monkeypatch.setattr("app.services.orchestrator._run_step", fake_run_step)
    monkeypatch.setattr("app.services.orchestrator._log", AsyncMock())

    await execute_hierarchical(sync_session, task, [ceo, planner, worker])

    assert task.status == TaskStatus.COMPLETED
    assert "HIERARCHICAL WORKFLOW COMPLETE" in task.final_output
    assert "CEO review" in task.final_output


# ==================== CEO Agent Tests ====================

@pytest.mark.asyncio
async def test_ceo_agent_analysis_mocked():
    """Test CEO requirement analysis with mocked LangChain invocation."""
    agent = Agent(name="CEO", endpoint="http://localhost:8000", role=AgentRole.CEO)
    project = Project(title="Test", client_requirements="Build a web app")

    ceo_manager = CeoAgentManager(agent)
    
    # Mock the ainvoke method to return a valid structured output
    mock_output = CeoAnalysisOutput(
        is_clear=True,
        clarification_questions=[],
        project_scope="A valid scope",
        complexity_estimate=5
    )
    
    with patch("langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock) as mock_ainvoke:
        mock_ainvoke.return_value = mock_output
        result = await ceo_manager.analyze_requirements(project)
        
        assert result.is_clear is True
        assert result.complexity_estimate == 5


# ==================== CTO Agent Tests ====================

@pytest.mark.asyncio
async def test_cto_agent_strategy_mocked():
    """Test CTO strategy generation with mocked LangChain invocation."""
    agent = Agent(name="CTO", endpoint="http://localhost:8000", role=AgentRole.CTO)
    project = Project(title="Test", client_requirements="Build a web app")
    planning_out = {"architecture": "microservices"}

    cto_manager = CTOAgentManager(agent)
    
    mock_output = CTOStrategyOutput(
        modules=[
            DerivedModule(name="Auth", description="OAuth2 module", technology="Python", complexity=6)
        ],
        strategy_notes="Focus on security"
    )
    
    with patch("langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock) as mock_ainvoke:
        mock_ainvoke.return_value = mock_output
        result = await cto_manager.define_modules(project, planning_out)
        
        assert len(result.modules) == 1
        assert result.modules[0].name == "Auth"
        assert result.strategy_notes == "Focus on security"


# ==================== Memory Manager Tests ====================

@pytest.mark.asyncio
async def test_memory_manager_keys():
    """Test Redis key format generation without needing a live Redis server."""
    mm = MemoryManager()
    assert mm._agent_key(42) == "lucy:agent:42:memory"
    assert mm._project_key(99) == "lucy:project:99:context"
