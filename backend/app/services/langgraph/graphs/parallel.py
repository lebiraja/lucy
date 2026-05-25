"""Parallel strategy graph — fan-out to all agents, then synthesize.

All agents receive the same prompt concurrently. An orchestrator agent
(if available) synthesizes the results; otherwise responses are concatenated.
"""

from __future__ import annotations

import asyncio

from langgraph.graph import StateGraph, START, END
from sqlalchemy import select

from app.database import async_session
from app.models import Agent, OperationalStatus
from app.services.langgraph.state import TaskState, AgentResult
from app.services.langgraph.nodes.agent_nodes import run_agent_step
from app.services.langgraph.nodes.utility_nodes import log_step
from app.services.langgraph.nodes.output_nodes import build_structured_output_node


async def parallel_fan_out_node(state: TaskState) -> dict:
    """Fan out prompt to all agents concurrently."""
    task_id = state["task_id"]
    agents = state["agents"]
    prompt = state["prompt"]
    workspace_dir = state.get("workspace_dir")
    conversation_history = state.get("conversation_history") or []

    await log_step(task_id, f"Starting PARALLEL execution with {len(agents)} agents")

    async def run_one(agent_dict: dict, order: int) -> AgentResult:
        return await run_agent_step(
            task_id, agent_dict, prompt, step_order=order,
            workspace_dir=workspace_dir,
            conversation_history=conversation_history,
        )

    results = await asyncio.gather(
        *[run_one(a, i) for i, a in enumerate(agents)],
        return_exceptions=True,
    )

    successful: list[AgentResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            await log_step(
                task_id,
                f"Agent {agents[i].get('name', 'unknown')} raised exception: {r}",
                level="error",
            )
        elif r.status == "completed":
            successful.append(r)

    if not successful:
        return {
            "task_status": "failed",
            "final_output": "All agents failed to respond.",
            "agent_responses": [],
        }

    await log_step(task_id, f"Collected {len(successful)} responses, aggregating...")
    return {"agent_responses": successful}


async def synthesize_parallel_node(state: TaskState) -> dict:
    """Use orchestrator agent to synthesize parallel results."""
    task_id = state["task_id"]
    responses = [r for r in state.get("agent_responses", []) if r.status == "completed"]

    if not responses:
        return {"task_status": "failed", "final_output": "No responses to synthesize."}

    # Find orchestrator agent (fresh session avoids stale connections)
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(
                Agent.is_orchestrator == True,  # noqa: E712
                Agent.is_active == True,  # noqa: E712
                Agent.operational_status == OperationalStatus.ACTIVE,
            )
        )
        orch = result.scalar_one_or_none()

    if orch:
        synthesis_prompt = (
            f"You are Lucy, the orchestrator agent. Multiple AI agents were asked the following question:\n\n"
            f"ORIGINAL PROMPT: {state['prompt']}\n\n"
            f"Here are their responses:\n\n"
        )
        for r in responses:
            synthesis_prompt += f"--- {r.agent_name} ({r.model_name}) ---\n{r.response}\n\n"
        synthesis_prompt += (
            "Please synthesize these responses into a single, comprehensive, high-quality answer. "
            "Take the best parts from each response, resolve any contradictions, and produce the definitive answer."
        )

        orch_dict = {"id": orch.id, "name": orch.name, "role": orch.role.value}
        synth = await run_agent_step(
            task_id, orch_dict, synthesis_prompt, step_order=len(responses),
            workspace_dir=state.get("workspace_dir"),
        )

        if synth.status == "completed":
            return {"final_output": synth.response, "task_status": "completed"}

    # Fallback: concatenate responses
    combined = "\n\n---\n\n".join(
        f"**{r.agent_name}** ({r.model_name}):\n{r.response}" for r in responses
    )
    return {"final_output": combined, "task_status": "completed"}


def build_parallel_graph() -> StateGraph:
    graph = StateGraph(TaskState)
    graph.add_node("fan_out", parallel_fan_out_node)
    graph.add_node("synthesize", synthesize_parallel_node)
    graph.add_node("structured_output", build_structured_output_node)
    graph.add_edge(START, "fan_out")
    graph.add_edge("fan_out", "synthesize")
    graph.add_edge("synthesize", "structured_output")
    graph.add_edge("structured_output", END)
    return graph
