"""Agent CRUD and health check API routes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Agent
from app.schemas import AgentCreate, AgentUpdate, AgentResponse, AgentHealth
from app.services.llm_client import check_health

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Register a new LLM agent."""
    agent = Agent(**data.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all registered agents."""
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    return result.scalars().all()


@router.get("/health", response_model=list[AgentHealth])
async def check_all_health(db: AsyncSession = Depends(get_db)):
    """Health check all active agents in parallel."""
    result = await db.execute(select(Agent).where(Agent.is_active == True))
    agents = result.scalars().all()

    async def check_one(agent: Agent) -> AgentHealth:
        is_online, latency, error = await check_health(agent.endpoint)
        return AgentHealth(
            id=agent.id,
            name=agent.name,
            endpoint=agent.endpoint,
            is_online=is_online,
            latency_ms=latency,
            error=error,
        )

    results = await asyncio.gather(*[check_one(a) for a in agents])
    return list(results)


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


@router.get("/{agent_id}/health", response_model=AgentHealth)
async def check_agent_health(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Health check a specific agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    is_online, latency, error = await check_health(agent.endpoint)
    return AgentHealth(
        id=agent.id,
        name=agent.name,
        endpoint=agent.endpoint,
        is_online=is_online,
        latency_ms=latency,
        error=error,
    )
