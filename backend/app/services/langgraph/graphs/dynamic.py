"""Dynamic routing strategy graph — orchestrator decides sub-strategy.

The orchestrator agent analyzes the prompt and available agents, then
decides whether to route to sequential or parallel execution.
"""

from __future__ import annotations

import json

from langgraph.graph import StateGraph, START, END
from sqlalchemy import select

from app.database import async_session
from app.models import Agent, OperationalStatus
from app.services.langgraph.state import TaskState
from app.services.langgraph.nodes.agent_nodes import run_agent_step
from app.services.langgraph.nodes.routing_nodes import extract_json
from app.services.langgraph.nodes.utility_nodes import log_step
from app.services.langgraph.nodes.output_nodes import build_structured_output_node
from app.services.langgraph.graphs.sequential import sequential_chain_node
from app.services.langgraph.graphs.parallel import (
    parallel_fan_out_node,
    synthesize_parallel_node,
)


async def dynamic_router_node(state: TaskState) -> dict:
    """Ask orchestrator agent to decide routing strategy."""
    task_id = state["task_id"]

    # Find orchestrator (fresh session)
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(
                Agent.is_orchestrator == True,  # noqa: E712
                Agent.is_active == True,  # noqa: E712
                Agent.operational_status == OperationalStatus.ACTIVE,
            )
        )
        orch = result.scalar_one_or_none()

    if not orch:
        await log_step(
            task_id,
            "No orchestrator agent configured — falling back to parallel",
            level="warning",
        )
        return {
            "routing_decision": {
                "strategy": "parallel",
                "agent_ids": [a["id"] for a in state["agents"]],
            }
        }

    # Build catalog of non-orchestrator agents
    non_orch = [a for a in state["agents"] if a["id"] != orch.id]
    catalog = json.dumps(
        [
            {
                "id": a["id"],
                "name": a.get("name", "unknown"),
                "model": a.get("model_name", "unknown"),
                "role": a.get("role", "employee"),
                "description": a.get("description", "No description"),
            }
            for a in non_orch
        ],
        indent=2,
    )

    routing_prompt = (
        f"You are Lucy, the orchestrator of a multi-agent AI system. "
        f"You must decide how to handle the following user query by routing it to the appropriate agents.\n\n"
        f"USER QUERY: {state['prompt']}\n\n"
        f"AVAILABLE AGENTS:\n{catalog}\n\n"
        f"Respond with a JSON object with this exact structure:\n"
        f'{{"strategy": "sequential" or "parallel", "agent_ids": [list of agent IDs in order], '
        f'"reasoning": "brief explanation"}}\n\n'
        f"Only respond with the JSON object, nothing else."
    )

    orch_dict = {"id": orch.id, "name": orch.name, "role": orch.role.value}
    result = await run_agent_step(task_id, orch_dict, routing_prompt, step_order=0)

    if result.status == "failed":
        await log_step(
            task_id,
            "Orchestrator failed to route — falling back to parallel",
            level="warning",
        )
        return {
            "routing_decision": {
                "strategy": "parallel",
                "agent_ids": [a["id"] for a in non_orch],
            }
        }

    try:
        response_text = extract_json(result.response)
        decision = json.loads(response_text)
        await log_step(
            task_id,
            f"Orchestrator decided: {decision.get('strategy')} with agents {decision.get('agent_ids')}. "
            f"Reasoning: {decision.get('reasoning', 'N/A')}",
        )
        return {"routing_decision": decision}
    except (json.JSONDecodeError, KeyError) as e:
        await log_step(
            task_id,
            f"Failed to parse routing decision: {e}. Falling back to parallel.",
            level="warning",
        )
        return {
            "routing_decision": {
                "strategy": "parallel",
                "agent_ids": [a["id"] for a in non_orch],
            }
        }


def route_after_decision(state: TaskState) -> str:
    """Conditional edge: read routing_decision to select sub-strategy."""
    decision = state.get("routing_decision")
    if not decision or not isinstance(decision, dict):
        return "parallel"
    return decision.get("strategy", "parallel")


async def apply_sequential(state: TaskState) -> dict:
    """Filter agents by routing decision, then run sequential chain."""
    decision = state.get("routing_decision", {})
    selected_ids = decision.get("agent_ids", [])
    selected = [a for a in state["agents"] if a["id"] in selected_ids] or state["agents"]
    return await sequential_chain_node({**state, "agents": selected})


async def apply_parallel(state: TaskState) -> dict:
    """Filter agents by routing decision, then run parallel + synthesize."""
    decision = state.get("routing_decision", {})
    selected_ids = decision.get("agent_ids", [])
    selected = [a for a in state["agents"] if a["id"] in selected_ids] or state["agents"]
    fan_result = await parallel_fan_out_node({**state, "agents": selected})
    merged = {**state, **fan_result}
    return await synthesize_parallel_node(merged)


def build_dynamic_graph() -> StateGraph:
    graph = StateGraph(TaskState)

    graph.add_node("router", dynamic_router_node)
    graph.add_node("run_sequential", apply_sequential)
    graph.add_node("run_parallel", apply_parallel)
    graph.add_node("structured_output", build_structured_output_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_after_decision,
        {"sequential": "run_sequential", "parallel": "run_parallel"},
    )
    graph.add_edge("run_sequential", "structured_output")
    graph.add_edge("run_parallel", "structured_output")
    graph.add_edge("structured_output", END)

    return graph
