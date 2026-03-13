"""
LangGraph Workflow Engine for Hierarchical Multi-Agent Platform.

Manages the top-level state machine for a client project:
Intake -> Planning (Level 0.5) -> CEO Review -> CTO Strategy -> Delegation -> Execution -> Monitoring -> Completion.
"""

from typing import Dict, Any, List, TypedDict, Literal
from langgraph.graph import StateGraph, END
from datetime import datetime, timezone
import logging
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import (
    Project, ProjectStatus, PlanningSession, ProjectModule, 
    Agent, AgentRole, AgentMessage, MessageType, MessagePriority,
)
from app.agents.ceo_agent import CeoAgentManager
from app.agents.planning_agents import PlanningAgentManager
from app.agents.cto_agent import CTOAgentManager

logger = logging.getLogger(__name__)

# --- State Definition ---

class ProjectState(TypedDict):
    project_id: int
    ceo_agent_id: int | None
    status: ProjectStatus
    requirements: str

    # Planning phase outputs
    architecture: Dict[str, Any] | None
    workforce_estimate: Dict[str, int] | None
    
    # Validation flags
    planning_approved: bool
    agents_sufficient: bool
    
    # Execution
    modules: List[Dict[str, Any]]
    current_phase: str
    errors: List[str]


# --- Node Functions ---

async def intake_node(state: ProjectState) -> Dict[str, Any]:
    """CEO receives the project and formulates initial understanding."""
    logger.info(f"Project {state['project_id']}: CEO intake running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if project:
            project.status = ProjectStatus.INTAKE
            await session.commit()
    
    return {"current_phase": "intake"}


async def planning_node(state: ProjectState) -> Dict[str, Any]:
    """Level 0.5 agents design architecture and workforce estimates."""
    logger.info(f"Project {state['project_id']}: Planning phase running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if not project:
            return {"current_phase": "planning", "error": "Project not found"}
        
        # Update project status
        project.status = ProjectStatus.PLANNING
        await session.commit()
        
        # Get CEO agent for planning
        ceo_agent = await session.get(Agent, project.ceo_agent_id) if project.ceo_agent_id else None
        if not ceo_agent:
            # Find any active CEO
            result = await session.execute(
                select(Agent).where(Agent.role == AgentRole.CEO, Agent.is_active == True).limit(1)
            )
            ceo_agent = result.scalar_one_or_none()
        
        if ceo_agent:
            try:
                # Run planning agents
                planning_manager = PlanningAgentManager(ceo_agent)
                planning_output = await planning_manager.create_plan(project)
                
                # Save planning session
                planning_session = PlanningSession(
                    project_id=project.id,
                    architecture=planning_output.get("architecture"),
                    module_breakdown=planning_output.get("modules"),
                    tech_stack=planning_output.get("tech_stack"),
                    workforce_estimate=planning_output.get("workforce"),
                    risk_analysis=planning_output.get("risks"),
                    execution_plan=planning_output.get("execution_plan"),
                )
                session.add(planning_session)
                
                # Update project with complexity estimate
                project.estimated_complexity = planning_output.get("complexity", 5)
                project.required_agents = planning_output.get("workforce")
                
                await session.commit()
                
                return {
                    "current_phase": "planning",
                    "architecture": planning_output.get("architecture"),
                    "workforce_estimate": planning_output.get("workforce"),
                    "planning_session_id": planning_session.id,
                }
            except Exception as e:
                logger.error(f"Planning failed: {e}")
                return {"current_phase": "planning", "error": str(e)}
    
    return {"current_phase": "planning"}


async def ceo_review_node(state: ProjectState) -> Dict[str, Any]:
    """CEO reviews the plan and checks agent availability."""
    logger.info(f"Project {state['project_id']}: CEO review running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if not project:
            return {"current_phase": "ceo_review", "error": "Project not found"}
        
        # Update status to planning_review
        project.status = ProjectStatus.PLANNING_REVIEW
        await session.commit()
        
        # Get latest planning session
        result = await session.execute(
            select(PlanningSession)
            .where(PlanningSession.project_id == project.id)
            .order_by(PlanningSession.created_at.desc())
            .limit(1)
        )
        planning_session = result.scalar_one_or_none()
        
        if not planning_session:
            return {"current_phase": "ceo_review", "error": "No planning session found"}
        
        # Get CEO agent
        ceo_agent = await session.get(Agent, project.ceo_agent_id) if project.ceo_agent_id else None
        if not ceo_agent:
            result = await session.execute(
                select(Agent).where(Agent.role == AgentRole.CEO, Agent.is_active == True).limit(1)
            )
            ceo_agent = result.scalar_one_or_none()
        
        if ceo_agent:
            try:
                ceo_manager = CeoAgentManager(ceo_agent)
                review_result = await ceo_manager.review_plan(project, {
                    "architecture": planning_session.architecture,
                    "workforce_estimate": planning_session.workforce_estimate,
                })
                
                planning_approved = review_result.approved
                feedback = review_result.feedback if not planning_approved else None
                
                # Check agent availability
                from app.services.agent_registry import get_fleet_status
                fleet_status = await get_fleet_status(session)
                
                workforce = planning_session.workforce_estimate or {}
                agents_sufficient = True
                insufficient_roles = []
                
                for role, needed in workforce.items():
                    role_data = next((r for r in fleet_status.by_role if r.role.value == role), None)
                    if not role_data or role_data.ready < needed:
                        agents_sufficient = False
                        insufficient_roles.append(role)
                
                # Update planning session status
                planning_session.status = "completed" if planning_approved else "rejected"
                await session.commit()
                
                # Send notification if agents insufficient
                if not agents_sufficient:
                    alert = AgentMessage(
                        project_id=project.id,
                        message_type=MessageType.ADMIN_ALERT,
                        priority=MessagePriority.HIGH,
                        payload={
                            "notification_type": "insufficient_agents",
                            "project_id": project.id,
                            "project_title": project.title,
                            "message": f"Insufficient agents for roles: {', '.join(insufficient_roles)}",
                            "insufficient_roles": insufficient_roles,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    session.add(alert)
                    await session.commit()
                
                return {
                    "current_phase": "ceo_review",
                    "planning_approved": planning_approved,
                    "agents_sufficient": agents_sufficient,
                    "feedback": feedback,
                    "insufficient_roles": insufficient_roles,
                }
            except Exception as e:
                logger.error(f"CEO review failed: {e}")
                return {"current_phase": "ceo_review", "error": str(e)}
    
    return {"current_phase": "ceo_review"}


async def cto_strategy_node(state: ProjectState) -> Dict[str, Any]:
    """CTO breaks architecture into specific modules."""
    logger.info(f"Project {state['project_id']}: CTO strategy running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if not project:
            return {"current_phase": "technical_strategy", "error": "Project not found"}
        
        # Update status to technical_strategy
        project.status = ProjectStatus.TECHNICAL_STRATEGY
        await session.commit()
        
        # Get CTO agent (or use CEO if no CTO available)
        result = await session.execute(
            select(Agent).where(Agent.role == AgentRole.CTO, Agent.is_active == True).limit(1)
        )
        cto_agent = result.scalar_one_or_none()
        
        if not cto_agent:
            # Use CEO as fallback
            cto_agent = await session.get(Agent, project.ceo_agent_id)
        
        if cto_agent:
            try:
                cto_manager = CTOAgentManager(cto_agent)
                cto_output = await cto_manager.create_modules(project)
                
                # Create project modules
                modules_data = cto_output.get("modules", [])
                created_modules = []
                
                for mod in modules_data:
                    module = ProjectModule(
                        project_id=project.id,
                        name=mod.get("name", "Unnamed Module"),
                        description=mod.get("description"),
                        technology=mod.get("technology"),
                        complexity=mod.get("complexity", 5),
                    )
                    session.add(module)
                    created_modules.append({
                        "id": module.id,
                        "name": module.name,
                        "technology": module.technology,
                    })
                
                await session.commit()
                
                return {
                    "current_phase": "technical_strategy",
                    "modules": created_modules,
                }
            except Exception as e:
                logger.error(f"CTO strategy failed: {e}")
                return {"current_phase": "technical_strategy", "error": str(e)}
    
    return {"current_phase": "technical_strategy"}


async def manager_delegation_node(state: ProjectState) -> Dict[str, Any]:
    """Managers assign tasks to workers."""
    logger.info(f"Project {state['project_id']}: Manager delegation running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if not project:
            return {"current_phase": "delegation", "error": "Project not found"}
        
        # Update status to in_progress
        project.status = ProjectStatus.IN_PROGRESS
        await session.commit()
        
        # Get managers
        result = await session.execute(
            select(Agent).where(Agent.role == AgentRole.MANAGER, Agent.is_active == True)
        )
        managers = result.scalars().all()
        
        # Assign modules to managers
        modules_result = await session.execute(
            select(ProjectModule).where(ProjectModule.project_id == project.id)
        )
        modules = modules_result.scalars().all()
        
        for i, module in enumerate(modules):
            if i < len(managers):
                module.assigned_manager_id = managers[i].id
                module.status = "assigned"
        
        await session.commit()
        
        return {
            "current_phase": "delegation",
            "assigned_modules": len(modules),
            "managers_count": len(managers),
        }


async def execution_monitoring_node(state: ProjectState) -> Dict[str, Any]:
    """Workers execute, managers monitor, CTO/CEO rollup."""
    logger.info(f"Project {state['project_id']}: Execution running.")
    
    async with async_session() as session:
        project = await session.get(Project, state['project_id'])
        if not project:
            return {"current_phase": "execution", "error": "Project not found"}
        
        # Update status to monitoring
        project.status = ProjectStatus.MONITORING
        await session.commit()
        
        # In a real implementation, this would monitor task progress
        # For now, we'll mark as completed
        project.status = ProjectStatus.COMPLETED
        project.completed_at = datetime.now(timezone.utc)
        await session.commit()
        
        return {"current_phase": "execution", "status": ProjectStatus.COMPLETED.value}


async def admin_alert_node(state: ProjectState) -> Dict[str, Any]:
    """Send alert to admin about insufficient agents, park project."""
    logger.info(f"Project {state['project_id']}: Sending ADMIN ALERT.")
    return {"current_phase": "on_hold", "status": ProjectStatus.ON_HOLD}


# --- Edge Condition Logic ---

def route_after_planning(state: ProjectState) -> Literal["ceo_review"]:
    return "ceo_review"

def route_after_ceo_review(state: ProjectState) -> Literal["cto_strategy", "planning_node", "admin_alert"]:
    if not state.get("planning_approved", False):
        return "planning_node"  # Re-plan
    if not state.get("agents_sufficient", False):
        return "admin_alert"    # Hold for admin
    return "cto_strategy"


# --- Graph Definition ---

def create_project_workflow() -> StateGraph:
    """Creates the LangGraph state machine for project orchestration."""
    graph = StateGraph(ProjectState)

    # Add Nodes
    graph.add_node("intake", intake_node)
    graph.add_node("planning_node", planning_node)
    graph.add_node("ceo_review", ceo_review_node)
    graph.add_node("cto_strategy", cto_strategy_node)
    graph.add_node("manager_delegation", manager_delegation_node)
    graph.add_node("execution_monitoring", execution_monitoring_node)
    graph.add_node("admin_alert", admin_alert_node)

    # Set Entry Point
    graph.set_entry_point("intake")

    # Add Edges
    graph.add_edge("intake", "planning_node")
    graph.add_edge("planning_node", "ceo_review")
    
    # Conditional edge after CEO review
    graph.add_conditional_edges(
        "ceo_review",
        route_after_ceo_review,
        {
            "cto_strategy": "cto_strategy",
            "planning_node": "planning_node",
            "admin_alert": "admin_alert"
        }
    )

    graph.add_edge("admin_alert", END) # Halts here until admin fixes it and resumes
    
    graph.add_edge("cto_strategy", "manager_delegation")
    graph.add_edge("manager_delegation", "execution_monitoring")
    graph.add_edge("execution_monitoring", END)

    return graph.compile()
