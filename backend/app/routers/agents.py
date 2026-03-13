"""Agent CRUD, health check, and hierarchy API routes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent, AgentRole, OperationalStatus, InfrastructureStatus, AgentState
from app.schemas import (
    AgentCreate, AgentUpdate, AgentResponse, AgentHealth,
    AgentFleetStatus, AgentRegister,
    BulkRegisterRequest, BulkRegisterResponse, BulkRegisterResult,
    AgentRetrainRequest, FleetSummaryResponse,
)
from app.services.llm_client import check_health, fetch_model_info
from app.services.agent_registry import get_fleet_status, get_available_agents, get_fleet_summary

router = APIRouter(prefix="/api/agents", tags=["agents"])



@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Register a new LLM agent. Auto-detects model_name and context_window from endpoint if not provided."""
    agent_data = data.model_dump()

    # Auto-detect model name and context window from endpoint
    if not agent_data.get("model_name") or not agent_data.get("context_window_tokens"):
        try:
            info = await fetch_model_info(data.endpoint)
            if not agent_data.get("model_name"):
                agent_data["model_name"] = info["model_name"]
            if not agent_data.get("context_window_tokens") and info.get("context_window"):
                agent_data["context_window_tokens"] = info["context_window"]
                # Adjust max_tokens based on detected context window
                # Use 40% of context for output, minimum 256
                agent_data["max_tokens"] = max(min(int(info["context_window"] * 0.4), 2048), 256)
        except Exception as e:
            # Not a hard error — just leave model_name/context_window as defaults
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


@router.get("/{agent_id}/performance")
async def get_agent_performance(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Get performance statistics for a specific agent."""
    from app.services.model_monitor import performance_tracker
    
    # Verify agent exists
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    stats = performance_tracker.get_agent_stats(agent_id)
    
    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "model_name": agent.model_name,
        "context_window": agent.context_window_tokens,
        "max_tokens": agent.max_tokens,
        "crash_count": agent.crash_count,
        "infrastructure_status": agent.infrastructure_status.value,
        "avg_response_time_ms": agent.avg_response_time_ms,
        "performance": stats,
    }


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


@router.get("/fleet-status", response_model=AgentFleetStatus)
async def fleet_status(db: AsyncSession = Depends(get_db)):
    """CEO fleet overview — counts of ready/under_review/offline agents by role."""
    return await get_fleet_status(db)


@router.get("/fleet-summary", response_model=FleetSummaryResponse)
async def fleet_summary(db: AsyncSession = Depends(get_db)):
    """CEO deep fleet overview — agents grouped by role with details + workforce demand."""
    return await get_fleet_summary(db)


@router.post("/bulk-register", response_model=BulkRegisterResponse, status_code=201)
async def bulk_register_agents(data: BulkRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Bulk-register agents — all join as generic EMPLOYEE workers. CEO assigns roles later."""
    results = []
    registered = 0
    failed = 0

    for item in data.agents:
        try:
            # Check for existing
            existing = await db.execute(
                select(Agent).where(Agent.endpoint == item.endpoint)
            )
            if existing.scalar_one_or_none():
                results.append(BulkRegisterResult(
                    name=item.name, endpoint=item.endpoint,
                    success=False, error="Agent with this endpoint already exists",
                ))
                failed += 1
                continue

            # Auto-detect model and context
            model_name = None
            context_window = 4096
            max_tokens = 2048
            try:
                info = await fetch_model_info(item.endpoint)
                model_name = info.get("model_name")
                if info.get("context_window"):
                    context_window = int(info.get("context_window"))
                    # Allocate a safe output fraction to avoid context overflow
                    max_tokens = max(min(int(context_window * 0.4), 2048), 256)
            except Exception:
                pass

            # Probe health
            infra = InfrastructureStatus.OFFLINE
            is_warm = False
            try:
                is_online, _, _ = await check_health(item.endpoint)
                if is_online:
                    infra = InfrastructureStatus.ONLINE
                    is_warm = True
            except Exception:
                pass

            agent = Agent(
                name=item.name,
                endpoint=item.endpoint,
                model_name=model_name,
                description=item.description,
                role=AgentRole.EMPLOYEE,  # Always employee — CEO assigns later
                context_window_tokens=context_window,
                max_tokens=max_tokens,
                infrastructure_status=infra,
                is_warm=is_warm,
            )
            db.add(agent)
            await db.flush()
            await db.refresh(agent)

            results.append(BulkRegisterResult(
                name=item.name, endpoint=item.endpoint,
                success=True, agent_id=agent.id, model_name=model_name,
            ))
            registered += 1
        except Exception as e:
            results.append(BulkRegisterResult(
                name=item.name, endpoint=item.endpoint,
                success=False, error=str(e),
            ))
            failed += 1

    return BulkRegisterResponse(registered=registered, failed=failed, results=results)


@router.post("/{agent_id}/retrain", response_model=AgentResponse)
async def retrain_agent(
    agent_id: int,
    data: AgentRetrainRequest,
    db: AsyncSession = Depends(get_db),
):
    """CEO retrains an agent — assigns new role, updates config, feeds context."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.role = data.role
    if data.parent_id is not None:
        agent.parent_id = data.parent_id
    if data.description is not None:
        agent.description = data.description
    if data.temperature is not None:
        agent.temperature = data.temperature
    if data.max_tokens is not None:
        agent.max_tokens = data.max_tokens

    # Dynamic agent label update for role awareness in conversations
    base_name = agent.name.split('|')[0].strip() if '|' in agent.name else agent.name
    agent.name = f"{agent.role.value.upper()} | {base_name}"

    await db.flush()
    await db.refresh(agent)
    return agent


@router.post("/register", response_model=AgentResponse, status_code=201)
async def register_agent(data: AgentRegister, db: AsyncSession = Depends(get_db)):
    """Self-registration endpoint — agents join the network dynamically via IP."""
    # Check if agent with same endpoint already exists
    result = await db.execute(
        select(Agent).where(Agent.endpoint == data.endpoint)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Update existing agent's status back to active
        existing.is_active = True
        existing.operational_status = OperationalStatus.ACTIVE
        existing.name = data.name
        existing.role = data.role
        if data.description:
            existing.description = data.description
        # Probe health
        try:
            is_online, latency, _ = await check_health(data.endpoint)
            existing.infrastructure_status = (
                InfrastructureStatus.ONLINE if is_online else InfrastructureStatus.OFFLINE
            )
            existing.is_warm = is_online
        except Exception:
            pass
        await db.flush()
        await db.refresh(existing)
        return existing

    # Create new agent
    agent_data = data.model_dump()
    try:
        info = await fetch_model_info(data.endpoint)
        agent_data["model_name"] = info.get("model_name")
        if info.get("context_window"):
            agent_data["context_window_tokens"] = int(info["context_window"])
            agent_data["max_tokens"] = max(min(int(agent_data["context_window_tokens"] * 0.4), 2048), 256)
    except Exception:
        agent_data["model_name"] = None

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


@router.get("/discover")
async def discover_agents(
    role: AgentRole | None = None,
    count: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Discover available agents, optionally filtered by role."""
    agents = await get_available_agents(db, role=role, count=count)
    return [
        {
            "id": a.id,
            "name": a.name,
            "endpoint": a.endpoint,
            "role": a.role.value,
            "model_name": a.model_name,
            "state": a.state.value,
        }
        for a in agents
    ]


@router.post("/{agent_id}/assign-role", response_model=AgentResponse)
async def assign_role(
    agent_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Assign a role to an agent at runtime."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    role_str = data.get("role", "").lower()
    try:
        agent.role = AgentRole(role_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role_str}'. Valid: {[r.value for r in AgentRole]}"
        )

    parent_id = data.get("parent_id")
    if parent_id is not None:
        agent.parent_id = parent_id

    # Dynamic agent label update for role awareness in conversations
    base_name = agent.name.split('|')[0].strip() if '|' in agent.name else agent.name
    agent.name = f"{agent.role.value.upper()} | {base_name}"

    await db.flush()
    await db.refresh(agent)
    return agent


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


@router.post("/{agent_id}/chat/stream")
async def stream_chat_completion(agent_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """
    Stream a chat completion from an agent in real-time.
    
    Request body:
    {
        "messages": [{"role": "user", "content": "..."}],
        "temperature": 0.7,  // optional
        "max_tokens": 512    // optional
    }
    
    Returns Server-Sent Events with chunks of text as they're generated.
    """
    from fastapi.responses import StreamingResponse
    from app.services.llm_client import chat_completion_stream
    import json
    
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.operational_status != OperationalStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Agent is {agent.operational_status.value}")
    
    if agent.infrastructure_status != InfrastructureStatus.ONLINE:
        raise HTTPException(status_code=503, detail="Agent is offline")
    
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="Messages are required")
    
    temperature = data.get("temperature")
    max_tokens = data.get("max_tokens")
    
    async def event_generator():
        try:
            async for chunk in chat_completion_stream(
                agent=agent,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                payload = json.dumps(chunk)
                yield f"data: {payload}\n\n"
                
                if chunk.get("done"):
                    break
        except Exception as e:
            error_payload = json.dumps({
                "error": str(e),
                "done": True,
            })
            yield f"data: {error_payload}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )



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
