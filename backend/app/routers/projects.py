"""Project CRUD and workflow API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Agent, AgentRole, OperationalStatus, InfrastructureStatus, AgentState,
    Project, ProjectStatus, ProjectModule, PlanningSession, AgentMessage, Task, TaskStep,
    TaskChatMessage, AuditLog, MessageType, MessagePriority,
)
from app.schemas import (
    ProjectCreate, ProjectResponse, ProjectModuleResponse,
    PlanningSessionResponse, AgentMessageResponse, TaskResponse,
    ProjectStrategy, AgentAssignmentRequest, AgentAssignmentResult,
    AvailabilityNotification, ChatMessageCreate, ChatMessageResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Submit a new client project. CEO agent will pick it up for processing."""
    # Find a CEO agent to assign
    result = await db.execute(
        select(Agent).where(
            Agent.role == AgentRole.CEO,
            Agent.is_active == True,
        ).limit(1)
    )
    ceo_agent = result.scalar_one_or_none()

    project = Project(
        title=data.title,
        client_requirements=data.client_requirements,
        deadline=data.deadline,
        status=ProjectStatus.INTAKE,
        ceo_agent_id=ceo_agent.id if ceo_agent else None,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(
        select(Project)
        .order_by(Project.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/modules", response_model=list[ProjectModuleResponse])
async def get_project_modules(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get all modules for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(ProjectModule)
        .where(ProjectModule.project_id == project_id)
        .order_by(ProjectModule.id)
    )
    return result.scalars().all()


@router.get("/{project_id}/planning", response_model=list[PlanningSessionResponse])
async def get_planning_sessions(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get all planning sessions for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(PlanningSession)
        .where(PlanningSession.project_id == project_id)
        .order_by(PlanningSession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}/messages", response_model=list[AgentMessageResponse])
async def get_project_messages(
    project_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get all agent messages for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.project_id == project_id)
        .order_by(AgentMessage.timestamp.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{project_id}/status")
async def get_project_status(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get real-time project status with hierarchy breakdown."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get modules
    modules_result = await db.execute(
        select(ProjectModule).where(ProjectModule.project_id == project_id)
    )
    modules = modules_result.scalars().all()

    # Calculate progress
    total_modules = len(modules)
    completed_modules = sum(1 for m in modules if m.status.value == "completed")
    progress_pct = round((completed_modules / total_modules * 100), 1) if total_modules > 0 else 0

    return {
        "project_id": project.id,
        "title": project.title,
        "status": project.status.value,
        "progress_percent": progress_pct,
        "total_modules": total_modules,
        "completed_modules": completed_modules,
        "ceo_agent_id": project.ceo_agent_id,
        "required_agents": project.required_agents,
        "deadline": project.deadline.isoformat() if project.deadline else None,
    }


@router.get("/{project_id}/tasks", response_model=list[TaskResponse])
async def get_project_tasks(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get all orchestration tasks for a project, including per-step agent details."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.steps).joinedload(TaskStep.agent))
        .where(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()

    response = []
    for task in tasks:
        task_resp = TaskResponse.model_validate(task)
        # Step agents are included via joinedload; add extra fields for client convenience.
        for step in task_resp.steps:
            if step.agent_id is not None:
                orm_step = next((s for s in task.steps if s.id == step.id), None)
                if orm_step and orm_step.agent:
                    step.agent_name = orm_step.agent.name
                    step.agent_role = orm_step.agent.role.value
        response.append(task_resp)

    return response


@router.post("/{project_id}/assign-ceo")
async def assign_ceo(project_id: int, ceo_agent_id: int, db: AsyncSession = Depends(get_db)):
    """Assign a specific CEO agent to a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    agent = await db.get(Agent, ceo_agent_id)
    if not agent or agent.role != AgentRole.CEO:
        raise HTTPException(status_code=400, detail="Invalid CEO agent ID provided.")
        
    project.ceo_agent_id = ceo_agent_id
    await db.commit()
    return {"status": "success", "ceo_agent_id": ceo_agent_id}


@router.post("/{project_id}/start-planning")
async def start_planning(project_id: int, db: AsyncSession = Depends(get_db)):
    """Triggers the workflow engine to start the planning phase."""
    from app.services.workflow_engine import create_project_workflow, ProjectState
    from app.models import ProjectStatus
    
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.ceo_agent_id:
        raise HTTPException(status_code=400, detail="Project requires a CEO to start planning.")

    # Update project status
    project.status = ProjectStatus.PLANNING
    await db.commit()

    # Create and run workflow
    workflow = create_project_workflow()
    
    initial_state = ProjectState(
        project_id=project_id,
        ceo_agent_id=project.ceo_agent_id,
        status=ProjectStatus.PLANNING,
        requirements=project.client_requirements,
        architecture=None,
        workforce_estimate=None,
        planning_approved=False,
        agents_sufficient=False,
        modules=[],
        current_phase="planning",
        errors=[],
    )
    
    # Run workflow in background (in production, use Celery/Redis Queue)
    try:
        result = await workflow.ainvoke(initial_state)
        return {
            "status": "success", 
            "workflow_result": result,
            "message": "Workflow executed. Check project status for updates.",
        }
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


# ---------- Agent Assignment & Strategy Endpoints ----------

@router.post("/{project_id}/select-strategy", response_model=dict)
async def select_project_strategy(
    project_id: int,
    strategy: ProjectStrategy,
    db: AsyncSession = Depends(get_db),
):
    """CEO selects strategy for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Store strategy in project metadata
    if project.task_metadata is None:
        project.task_metadata = {}
    
    project.task_metadata["strategy"] = strategy.model_dump()
    project.task_metadata["priority"] = strategy.priority
    project.task_metadata["estimated_duration_days"] = strategy.estimated_duration_days
    
    await db.commit()
    await db.refresh(project)

    # Log audit trail
    audit = AuditLog(
        agent_id=project.ceo_agent_id,
        action_type="strategy_selected",
        entity_type="project",
        entity_id=project_id,
        task_metadata=strategy.model_dump(),
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "strategy": strategy.strategy_type.value,
        "priority": strategy.priority,
    }


@router.post("/{project_id}/assign-agents", response_model=AgentAssignmentResult)
async def assign_agents_to_project(
    project_id: int,
    assignment: AgentAssignmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    CEO assigns agents to a project manually.
    If agents are not available, returns warning with insufficient agents.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assigned_agents = []
    unassigned_agents = []
    warnings = []

    for agent_assignment in assignment.agents:
        agent = await db.get(Agent, agent_assignment.agent_id)
        if not agent:
            unassigned_agents.append({
                "agent_id": agent_assignment.agent_id,
                "reason": "Agent not found",
            })
            continue

        # Check if agent is available
        if agent.operational_status != OperationalStatus.ACTIVE:
            unassigned_agents.append({
                "agent_id": agent_assignment.agent_id,
                "reason": f"Agent is {agent.operational_status.value}",
            })
            warnings.append(f"Agent {agent.name} is {agent.operational_status.value}")
            continue

        if agent.infrastructure_status != InfrastructureStatus.ONLINE:
            unassigned_agents.append({
                "agent_id": agent_assignment.agent_id,
                "reason": "Agent is offline",
            })
            warnings.append(f"Agent {agent.name} is offline")
            continue

        # Assign agent to project
        agent.state = AgentState.ASSIGNED
        agent.operational_status = OperationalStatus.ACTIVE
        
        # If agent is CEO, assign to project
        if agent.role == AgentRole.CEO:
            project.ceo_agent_id = agent.id
        
        assigned_agents.append({
            "agent_id": agent.id,
            "agent_name": agent.name,
            "role": agent.role.value,
            "assigned_role": agent_assignment.role_on_project or agent.role.value,
        })

    # Apply strategy if provided
    if assignment.strategy:
        if project.task_metadata is None:
            project.task_metadata = {}
        project.task_metadata["strategy"] = assignment.strategy.model_dump()

    await db.commit()

    # Send notification if there are unassigned agents
    if unassigned_agents:
        notification = {
            "notification_type": "insufficient_agents",
            "project_id": project_id,
            "project_title": project.title,
            "message": f"Could not assign {len(unassigned_agents)} agent(s) to project",
            "timestamp": project.created_at.isoformat() if project.created_at else None,
        }
        # Store as project message
        msg = AgentMessage(
            project_id=project_id,
            message_type=MessageType.ADMIN_ALERT,
            priority=MessagePriority.HIGH,
            payload=notification,
        )
        db.add(msg)
        await db.commit()

    return AgentAssignmentResult(
        project_id=project_id,
        assigned_agents=assigned_agents,
        unassigned_agents=unassigned_agents,
        warnings=warnings,
    )


@router.post("/{project_id}/auto-assign-agents", response_model=AgentAssignmentResult)
async def auto_assign_idle_agents(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Auto-assign idle agents to a project.
    Prioritizes warm, online agents in IDLE state.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get required roles from project metadata or planning
    required_roles = project.required_agents or {}
    if not required_roles:
        # Default: need 1 CEO, 1 CTO, 2 managers, 5 employees
        required_roles = {
            "ceo": 1,
            "cto": 1,
            "manager": 2,
            "employee": 5,
        }

    assigned_agents = []
    unassigned_roles = []
    auto_assigned_count = 0

    for role_name, needed_count in required_roles.items():
        try:
            role = AgentRole(role_name.lower())
        except ValueError:
            unassigned_roles.append({"role": role_name, "reason": "Invalid role"})
            continue

        # Find idle agents with this role
        result = await db.execute(
            select(Agent)
            .where(
                Agent.role == role,
                Agent.operational_status == OperationalStatus.ACTIVE,
                Agent.infrastructure_status == InfrastructureStatus.ONLINE,
                Agent.state == AgentState.IDLE,
            )
            .order_by(Agent.is_warm.desc(), Agent.created_at.asc())
            .limit(needed_count)
        )
        available_agents = result.scalars().all()

        assigned_count = len(available_agents)
        missing_count = needed_count - assigned_count

        for agent in available_agents:
            agent.state = AgentState.ASSIGNED
            assigned_agents.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": agent.role.value,
                "auto_assigned": True,
            })
            auto_assigned_count += 1

        if missing_count > 0:
            unassigned_roles.append({
                "role": role_name,
                "needed": needed_count,
                "assigned": assigned_count,
                "missing": missing_count,
            })

    # If CEO not assigned, find any available CEO
    if not project.ceo_agent_id:
        ceo_result = await db.execute(
            select(Agent)
            .where(
                Agent.role == AgentRole.CEO,
                Agent.operational_status == OperationalStatus.ACTIVE,
                Agent.infrastructure_status == InfrastructureStatus.ONLINE,
            )
            .limit(1)
        )
        ceo = ceo_result.scalar_one_or_none()
        if ceo:
            ceo.state = AgentState.ASSIGNED
            project.ceo_agent_id = ceo.id
            assigned_agents.append({
                "agent_id": ceo.id,
                "agent_name": ceo.name,
                "role": "ceo",
                "auto_assigned": True,
            })

    await db.commit()

    # Send notification to CEO about auto-assignment
    if auto_assigned_count > 0:
        notification = {
            "notification_type": "auto_assigned",
            "project_id": project_id,
            "project_title": project.title,
            "message": f"Auto-assigned {auto_assigned_count} idle agent(s) to project",
            "available_agents": assigned_agents,
            "required_roles": required_roles,
            "timestamp": project.created_at.isoformat() if project.created_at else None,
        }
        
        # Create audit log
        audit = AuditLog(
            agent_id=project.ceo_agent_id,
            action_type="auto_assign_agents",
            entity_type="project",
            entity_id=project_id,
            task_metadata=notification,
        )
        db.add(audit)
        
        # Create message
        msg = AgentMessage(
            project_id=project_id,
            message_type=MessageType.STATUS_REPORT,
            priority=MessagePriority.NORMAL,
            payload=notification,
        )
        db.add(msg)

    # Warn if roles couldn't be filled
    warnings = []
    if unassigned_roles:
        for unassigned in unassigned_roles:
            warnings.append(
                f"Role {unassigned['role']}: needed {unassigned.get('needed', 1)}, "
                f"assigned {unassigned.get('assigned', 0)}, "
                f"missing {unassigned.get('missing', 1)}"
            )
        
        # Send insufficient agents alert
        if project.ceo_agent_id:
            alert = {
                "notification_type": "insufficient_agents",
                "project_id": project_id,
                "project_title": project.title,
                "message": "Insufficient agents available for required roles",
                "required_roles": required_roles,
                "timestamp": project.created_at.isoformat() if project.created_at else None,
            }
            msg = AgentMessage(
                project_id=project_id,
                receiver_id=project.ceo_agent_id,
                message_type=MessageType.ADMIN_ALERT,
                priority=MessagePriority.HIGH,
                payload=alert,
            )
            db.add(msg)

    await db.commit()

    return AgentAssignmentResult(
        project_id=project_id,
        assigned_agents=assigned_agents,
        unassigned_agents=unassigned_roles,
        warnings=warnings,
        auto_assigned=True,
    )


@router.get("/{project_id}/availability-check")
async def check_agent_availability(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Check agent availability for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    required_roles = project.required_agents or {
        "ceo": 1, "cto": 1, "manager": 2, "employee": 5,
    }

    availability = {}
    available_agents = []

    for role_name, needed_count in required_roles.items():
        try:
            role = AgentRole(role_name.lower())
        except ValueError:
            continue

        result = await db.execute(
            select(Agent)
            .where(
                Agent.role == role,
                Agent.operational_status == OperationalStatus.ACTIVE,
                Agent.infrastructure_status == InfrastructureStatus.ONLINE,
                Agent.state.in_([AgentState.IDLE, AgentState.COMPLETED]),
            )
        )
        agents = result.scalars().all()

        availability[role_name] = {
            "needed": needed_count,
            "available": len(agents),
            "sufficient": len(agents) >= needed_count,
        }

        for agent in agents:
            available_agents.append({
                "id": agent.id,
                "name": agent.name,
                "role": agent.role.value,
                "state": agent.state.value,
                "is_warm": agent.is_warm,
            })

    # Check if all roles are satisfied
    all_sufficient = all(v["sufficient"] for v in availability.values())
    
    insufficient_roles = [
        role for role, data in availability.items() 
        if not data["sufficient"]
    ]

    return {
        "project_id": project_id,
        "project_title": project.title,
        "all_roles_satisfied": all_sufficient,
        "availability": availability,
        "insufficient_roles": insufficient_roles,
        "available_agents": available_agents,
        "total_available": len(available_agents),
        "total_needed": sum(required_roles.values()),
    }


@router.get("/{project_id}/notifications")
async def get_project_notifications(
    project_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Get all notifications/alerts for a project (for CEO dashboard)."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(AgentMessage)
        .where(
            AgentMessage.project_id == project_id,
            AgentMessage.message_type.in_([
                MessageType.ADMIN_ALERT,
                MessageType.STATUS_REPORT,
                MessageType.PROGRESS_UPDATE,
            ]),
        )
        .order_by(AgentMessage.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        {
            "id": msg.id,
            "type": msg.message_type.value,
            "priority": msg.priority.value,
            "payload": msg.payload,
            "timestamp": msg.timestamp.isoformat(),
            "is_read": msg.is_read,
        }
        for msg in messages
    ]


# ---------- Task Chat Endpoints ----------

@router.get("/{project_id}/tasks/{task_id}/chat")
async def get_task_chat(
    project_id: int,
    task_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get chat messages for a task."""
    # Verify project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify task belongs to project
    task = await db.get(Task, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(TaskChatMessage)
        .where(TaskChatMessage.task_id == task_id)
        .order_by(TaskChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    response = []
    for msg in messages:
        response.append({
            "id": msg.id,
            "task_id": msg.task_id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender.name if msg.sender else None,
            "sender_role": msg.sender.role.value if msg.sender else None,
            "message": msg.message,
            "message_type": msg.message_type,
            "timestamp": msg.created_at.isoformat(),
        })

    return list(reversed(response))  # Return in chronological order


@router.post("/{project_id}/tasks/{task_id}/chat", response_model=ChatMessageResponse)
async def send_task_chat_message(
    project_id: int,
    task_id: int,
    chat_msg: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message on a task page."""
    # Verify project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify task belongs to project
    task = await db.get(Task, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify sender if provided
    sender = None
    if chat_msg.sender_id:
        sender = await db.get(Agent, chat_msg.sender_id)
        if not sender:
            raise HTTPException(status_code=404, detail="Sender agent not found")

    # Create chat message
    message = TaskChatMessage(
        task_id=task_id,
        sender_id=chat_msg.sender_id,
        message=chat_msg.message,
        message_type=chat_msg.message_type,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return ChatMessageResponse(
        id=message.id,
        task_id=message.task_id,
        sender_id=message.sender_id,
        sender_name=sender.name if sender else None,
        sender_role=sender.role.value if sender else None,
        message=message.message,
        message_type=message.message_type,
        timestamp=message.created_at,
    )
