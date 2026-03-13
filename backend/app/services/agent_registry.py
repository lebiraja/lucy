"""
Agent Registry Service — Dynamic agent discovery and fleet status for CEO awareness.

Provides:
  - Fleet status (ready/under_review/offline counts by role)
  - Agent discovery by role and availability
  - Workforce sufficiency checks
  - Admin alerts when agents are insufficient
"""

from collections import defaultdict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent, AgentRole, AgentState,
    OperationalStatus, InfrastructureStatus,
    AgentMessage, MessageType, MessagePriority,
)
from app.schemas import AgentFleetStatus, AgentRoleCount
from app.services.logger import log_broadcaster


async def get_fleet_status(session: AsyncSession) -> AgentFleetStatus:
    """
    Get a complete overview of the agent fleet — how many are ready,
    under review, or offline, grouped by role.

    This is what the CEO queries to understand available workforce.
    """
    result = await session.execute(select(Agent).where(Agent.is_active == True))
    agents = result.scalars().all()

    ready = 0
    under_review = 0
    offline = 0
    by_role: dict[AgentRole, dict] = defaultdict(
        lambda: {"ready": 0, "under_review": 0, "offline": 0, "total": 0}
    )

    for agent in agents:
        role = agent.role
        by_role[role]["total"] += 1

        if (
            agent.operational_status == OperationalStatus.ACTIVE
            and agent.infrastructure_status == InfrastructureStatus.ONLINE
            and agent.state in (AgentState.IDLE, AgentState.COMPLETED)
        ):
            ready += 1
            by_role[role]["ready"] += 1
        elif (
            agent.operational_status == OperationalStatus.PAUSED
            or agent.state in (AgentState.ASSIGNED, AgentState.PLANNING, AgentState.EXECUTING)
        ):
            under_review += 1
            by_role[role]["under_review"] += 1
        else:
            offline += 1
            by_role[role]["offline"] += 1

    role_counts = [
        AgentRoleCount(
            role=role,
            ready=counts["ready"],
            under_review=counts["under_review"],
            offline=counts["offline"],
            total=counts["total"],
        )
        for role, counts in by_role.items()
    ]

    return AgentFleetStatus(
        total_agents=len(agents),
        ready_count=ready,
        under_review_count=under_review,
        offline_count=offline,
        by_role=role_counts,
    )


async def get_available_agents(
    session: AsyncSession,
    role: AgentRole | None = None,
    count: int | None = None,
) -> list[Agent]:
    """
    Find available agents, optionally filtered by role.
    Returns agents that are ACTIVE + ONLINE + IDLE.
    """
    conditions = [
        Agent.is_active == True,
        Agent.operational_status == OperationalStatus.ACTIVE,
        Agent.infrastructure_status == InfrastructureStatus.ONLINE,
        Agent.state == AgentState.IDLE,
    ]
    if role is not None:
        conditions.append(Agent.role == role)

    query = select(Agent).where(and_(*conditions))
    if count is not None:
        query = query.limit(count)

    result = await session.execute(query)
    return list(result.scalars().all())


async def check_workforce_sufficiency(
    session: AsyncSession,
    required: dict[str, int],
) -> tuple[bool, list[str], dict[str, dict]]:
    """
    Compare required agent counts per role vs available agents.

    Args:
        required: e.g. {"cto": 1, "manager": 3, "employee": 8}

    Returns:
        (is_sufficient, insufficient_roles, details)
        details maps role -> {"required": N, "available": M, "deficit": D}
    """
    fleet = await get_fleet_status(session)
    role_ready = {rc.role.value: rc.ready for rc in fleet.by_role}

    insufficient_roles = []
    details = {}

    for role_str, needed in required.items():
        available = role_ready.get(role_str, 0)
        deficit = max(0, needed - available)
        details[role_str] = {
            "required": needed,
            "available": available,
            "deficit": deficit,
        }
        if deficit > 0:
            insufficient_roles.append(role_str)

    is_sufficient = len(insufficient_roles) == 0
    return is_sufficient, insufficient_roles, details


async def send_admin_alert(
    session: AsyncSession,
    message: str,
    project_id: int | None = None,
    details: dict | None = None,
):
    """
    CEO sends an alert to the admin (human operator) when agents are insufficient.
    Stores as an AgentMessage with type ADMIN_ALERT and broadcasts via WebSocket.
    """
    alert = AgentMessage(
        sender_id=None,  # System-level alert
        receiver_id=None,  # Goes to admin (human)
        project_id=project_id,
        message_type=MessageType.ADMIN_ALERT,
        payload={
            "message": message,
            "details": details or {},
        },
        priority=MessagePriority.CRITICAL,
    )
    session.add(alert)
    await session.flush()

    # Broadcast via WebSocket so frontend picks it up
    await log_broadcaster.broadcast(
        message=f"🚨 ADMIN ALERT: {message}",
        level="warning",
        source="ceo-agent",
        task_id=None,
    )

    return alert


async def get_fleet_summary(session: AsyncSession) -> "FleetSummaryResponse":
    """
    Deep fleet summary — agents grouped by role with individual details,
    plus workforce demand from active projects.
    This is the CEO's primary awareness endpoint.
    """
    from app.schemas import (
        FleetSummaryResponse, FleetRoleDetail, FleetAgentDetail,
        WorkforceDemand,
    )
    from app.models import Project, ProjectStatus

    # 1. Fetch all active agents
    result = await session.execute(select(Agent).where(Agent.is_active == True))
    agents = result.scalars().all()

    # 2. Build per-role breakdown
    role_data: dict[AgentRole, dict] = {}
    for role in AgentRole:
        role_data[role] = {"ready": 0, "busy": 0, "offline": 0, "total": 0, "agents": []}

    ready_total = 0
    busy_total = 0
    offline_total = 0
    unassigned = 0

    for agent in agents:
        role = agent.role
        role_data[role]["total"] += 1
        role_data[role]["agents"].append(FleetAgentDetail(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            state=agent.state,
            operational_status=agent.operational_status,
            infrastructure_status=agent.infrastructure_status,
            model_name=agent.model_name,
            is_warm=agent.is_warm,
        ))

        if (
            agent.operational_status == OperationalStatus.ACTIVE
            and agent.infrastructure_status == InfrastructureStatus.ONLINE
            and agent.state in (AgentState.IDLE, AgentState.COMPLETED)
        ):
            ready_total += 1
            role_data[role]["ready"] += 1
        elif agent.state in (AgentState.ASSIGNED, AgentState.PLANNING, AgentState.EXECUTING,
                              AgentState.DELEGATING, AgentState.WAITING, AgentState.REPORTING):
            busy_total += 1
            role_data[role]["busy"] += 1
        else:
            offline_total += 1
            role_data[role]["offline"] += 1

        # Count unassigned employees (potential for role assignment by CEO)
        if agent.role == AgentRole.EMPLOYEE and agent.parent_id is None:
            unassigned += 1

    by_role = [
        FleetRoleDetail(
            role=role,
            ready=data["ready"],
            busy=data["busy"],
            offline=data["offline"],
            total=data["total"],
            agents=data["agents"],
        )
        for role, data in role_data.items()
    ]

    # 3. Workforce demand from active projects
    active_statuses = [
        ProjectStatus.INTAKE, ProjectStatus.PLANNING, ProjectStatus.PLANNING_REVIEW,
        ProjectStatus.TECHNICAL_STRATEGY, ProjectStatus.IN_PROGRESS, ProjectStatus.MONITORING,
    ]
    proj_result = await session.execute(
        select(Project).where(Project.status.in_(active_statuses))
    )
    active_projects = proj_result.scalars().all()

    demands = []
    total_demand: dict[str, int] = defaultdict(int)
    for project in active_projects:
        req = project.required_agents or {}
        demands.append(WorkforceDemand(
            project_id=project.id,
            project_title=project.title,
            required=req,
        ))
        for r, count in req.items():
            total_demand[r] += count

    # 4. Check insufficient roles
    role_ready_map = {rd.role.value: rd.ready for rd in by_role}
    insufficient = [
        r for r, needed in total_demand.items()
        if role_ready_map.get(r, 0) < needed
    ]

    return FleetSummaryResponse(
        total_agents=len(agents),
        ready_count=ready_total,
        busy_count=busy_total,
        offline_count=offline_total,
        by_role=by_role,
        workforce_demand=demands,
        insufficient_roles=insufficient,
        unassigned_count=unassigned,
    )
