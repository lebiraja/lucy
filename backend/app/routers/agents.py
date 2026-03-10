"""Agent CRUD, health check, and hierarchy API routes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, OperationalStatus, InfrastructureStatus, AgentState, AgentRole
from app.schemas import (
    AgentCreate, AgentUpdate, AgentResponse, AgentHealth,
    AgentRegister, AgentRegisterResponse, AgentHeartbeat, AgentHeartbeatResponse
)
from app.services.llm_client import check_health, fetch_model_info

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Register a new LLM agent. Auto-detects model_name from endpoint if not provided."""
    agent_data = data.model_dump()

    # Auto-detect model name from endpoint
    if not agent_data.get("model_name"):
        try:
            info = await fetch_model_info(data.endpoint)
            agent_data["model_name"] = info["model_name"]
        except Exception as e:
            # Not a hard error — just leave model_name as None
            agent_data["model_name"] = None

    # Probe endpoint to set initial infrastructure status
    try:
        is_online, latency, _ = await check_health(data.endpoint)
        if is_online:
            agent_data["infrastructure_status"] = InfrastructureStatus.ONLINE
            agent_data["is_warm"] = True
    except Exception:
        pass

    agent = Agent(**agent_data)
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.post("/probe")
async def probe_endpoint(data: dict):
    """Probe a vLLM endpoint to discover available models."""
    endpoint = data.get("endpoint", "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="Endpoint URL is required")
    try:
        info = await fetch_model_info(endpoint)
        return {"success": True, **info}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all registered agents."""
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    return result.scalars().all()


@router.get("/health", response_model=list[AgentHealth])
async def check_all_health(db: AsyncSession = Depends(get_db)):
    """Health check all active agents in parallel and update infrastructure status."""
    result = await db.execute(select(Agent).where(Agent.is_active == True))
    agents = result.scalars().all()

    async def check_one(agent: Agent) -> AgentHealth:
        is_online, latency, error = await check_health(agent.endpoint)
        # Update infrastructure status in DB
        agent.infrastructure_status = (
            InfrastructureStatus.ONLINE if is_online else InfrastructureStatus.OFFLINE
        )
        agent.is_warm = is_online
        if is_online and latency:
            agent.avg_response_time_ms = latency
        return AgentHealth(
            id=agent.id,
            name=agent.name,
            endpoint=agent.endpoint,
            is_online=is_online,
            latency_ms=latency,
            error=error,
        )

    results = await asyncio.gather(*[check_one(a) for a in agents])
    await db.flush()
    return list(results)


@router.get("/hierarchy")
async def get_hierarchy(db: AsyncSession = Depends(get_db)):
    """Get agent hierarchy tree."""
    result = await db.execute(select(Agent).order_by(Agent.role, Agent.name))
    agents = result.scalars().all()

    def build_tree(parent_id=None):
        nodes = []
        for agent in agents:
            if agent.parent_id == parent_id:
                node = {
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role.value,
                    "operational_status": agent.operational_status.value,
                    "infrastructure_status": agent.infrastructure_status.value,
                    "state": agent.state.value,
                    "is_orchestrator": agent.is_orchestrator,
                    "children": build_tree(agent.id),
                }
                nodes.append(node)
        return nodes

    return build_tree(None)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific agent by ID."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: int, data: AgentUpdate, db: AsyncSession = Depends(get_db)):
    """Update an existing agent's configuration."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Remove an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Pause an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.operational_status = OperationalStatus.PAUSED
    agent.state = AgentState.STOPPED
    await db.flush()
    await db.refresh(agent)
    return agent


@router.post("/{agent_id}/resume", response_model=AgentResponse)
async def resume_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Resume a paused agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.operational_status = OperationalStatus.ACTIVE
    agent.state = AgentState.IDLE
    await db.flush()
    await db.refresh(agent)
    return agent


@router.post("/{agent_id}/stop", response_model=AgentResponse)
async def stop_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Stop an agent execution."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.operational_status = OperationalStatus.STOPPED
    agent.state = AgentState.STOPPED
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}/health", response_model=AgentHealth)
async def check_agent_health(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Health check a specific agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    is_online, latency, error = await check_health(agent.endpoint)
    # Update status
    agent.infrastructure_status = (
        InfrastructureStatus.ONLINE if is_online else InfrastructureStatus.OFFLINE
    )
    agent.is_warm = is_online
    await db.flush()

    return AgentHealth(
        id=agent.id,
        name=agent.name,
        endpoint=agent.endpoint,
        is_online=is_online,
        latency_ms=latency,
        error=error,
    )


@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
async def register_agent(data: AgentRegister, db: AsyncSession = Depends(get_db)):
    """Dynamic self-registration for agents."""
    import secrets
    from datetime import datetime, timezone
    
    agent_data = data.model_dump()
    
    # Auto-detect model if missing
    if not agent_data.get("model_name"):
        try:
            info = await fetch_model_info(data.endpoint)
            agent_data["model_name"] = info["model_name"]
        except Exception:
            agent_data["model_name"] = None

    # Determine hierarchy level based on role
    role_to_level = {
        AgentRole.CEO: 0,
        AgentRole.PLANNER: 1,
        AgentRole.QUESTIONER: 1,
        AgentRole.CTO: 2,
        AgentRole.CFO: 2,
        AgentRole.MANAGER: 3,
        AgentRole.HR_MANAGER: 3,
        AgentRole.BACKEND_MANAGER: 3,
        AgentRole.FRONTEND_MANAGER: 3,
        AgentRole.QA_MANAGER: 3,
        AgentRole.EMPLOYEE: 4,
        AgentRole.DEVELOPER: 4,
        AgentRole.TESTER: 4,
    }
    agent_data["hierarchy_level"] = role_to_level.get(data.role, 4)
    
    # Generate token
    token = secrets.token_urlsafe(32)
    agent_data["registration_token"] = token
    
    # Probe initial health
    try:
        is_online, latency, _ = await check_health(data.endpoint)
        if is_online:
            agent_data["infrastructure_status"] = InfrastructureStatus.ONLINE
            agent_data["is_warm"] = True
            agent_data["last_heartbeat"] = datetime.now(timezone.utc)
    except Exception:
        pass
        
    agent = Agent(**agent_data)
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    
    return AgentRegisterResponse(agent=agent, registration_token=token)


@router.post("/heartbeat", response_model=AgentHeartbeatResponse)
async def agent_heartbeat(data: AgentHeartbeat, db: AsyncSession = Depends(get_db)):
    """Receive periodic heartbeat from registered agents."""
    from datetime import datetime, timezone
    
    agent = await db.get(Agent, data.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    if agent.registration_token and agent.registration_token != data.registration_token:
        raise HTTPException(status_code=401, detail="Invalid registration token")
        
    now = datetime.now(timezone.utc)
    agent.last_heartbeat = now
    agent.infrastructure_status = InfrastructureStatus.ONLINE
    
    if data.status:
        agent.operational_status = data.status
        
    await db.flush()
    
    return AgentHeartbeatResponse(success=True, acknowledged_at=now)


@router.get("/discover", response_model=list[AgentResponse])
async def discover_agents(
    role: AgentRole | None = None,
    hierarchy_level: int | None = None,
    capability: str | None = None,
    is_online: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    """Discover agents matching criteria."""
    query = select(Agent)
    
    if role:
        query = query.where(Agent.role == role)
    if hierarchy_level is not None:
        query = query.where(Agent.hierarchy_level == hierarchy_level)
    if is_online is not None:
        status = InfrastructureStatus.ONLINE if is_online else InfrastructureStatus.OFFLINE
        query = query.where(Agent.infrastructure_status == status)
        
    result = await db.execute(query.order_by(Agent.name))
    agents = result.scalars().all()
    
    # Filter by capability (in python to avoid complex JSON containment queries across diff DBs)
    if capability:
        agents = [
            a for a in agents 
            if a.capabilities and capability in a.capabilities
        ]
        
    return agents
