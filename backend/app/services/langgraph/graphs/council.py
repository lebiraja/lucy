"""Council strategy subgraph — 3-stage CEO-led deliberation.

Stage 1: Individual opinions (parallel, role-aware prompts)
Stage 2: Anonymous blind peer review + structured ranking (parallel)
Stage 3: CEO/Chairman synthesis with full named context

This is the most complex LangGraph graph in the system, faithfully
porting the council logic from orchestrator.execute_council().
"""

from __future__ import annotations

import asyncio

from langgraph.graph import StateGraph, START, END
from sqlalchemy import select

from app.database import async_session
from app.models import Agent, OperationalStatus, Task
from app.services.langgraph.state import TaskState, AgentResult
from app.services.langgraph.nodes.agent_nodes import (
    run_agent_step,
    ROLE_SYSTEM_PROMPTS,
)
from app.services.langgraph.nodes.routing_nodes import (
    parse_ranking_from_text,
    calculate_aggregate_rankings,
)
from app.services.langgraph.nodes.utility_nodes import log_step


# ---------- Stage 1: Individual Opinions ----------

async def opinion_fan_out_node(state: TaskState) -> dict:
    """Stage 1: Collect individual opinions from all agents in parallel."""
    task_id = state["task_id"]
    agents = state["agents"]
    prompt = state["prompt"]

    await log_step(task_id, "📋 STAGE 1: Collecting individual opinions from all agents...")

    async def get_opinion(agent_dict: dict, order: int) -> AgentResult:
        role = agent_dict.get("role", "employee")
        role_prompt = ROLE_SYSTEM_PROMPTS.get(role, ROLE_SYSTEM_PROMPTS["employee"])
        full_prompt = (
            f"{role_prompt}\n\n"
            f"You are {agent_dict.get('name', 'Agent')} (Role: {role.upper()}).\n\n"
            f"Please provide your expert analysis of the following:\n\n"
            f"{prompt}"
        )
        return await run_agent_step(
            task_id, agent_dict, full_prompt, step_order=order, step_label="opinion",
        )

    results = await asyncio.gather(
        *[get_opinion(a, i) for i, a in enumerate(agents)],
        return_exceptions=True,
    )

    opinions: list[AgentResult] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            await log_step(
                task_id,
                f"Agent {agents[i].get('name', 'unknown')} failed in Stage 1: {result}",
                level="error",
            )
            continue
        if result.status == "completed":
            opinions.append(result)

    if not opinions:
        return {
            "council_opinions": [],
            "error": "All agents failed to provide opinions.",
        }

    await log_step(task_id, f"✓ Stage 1 complete — {len(opinions)} opinions collected")
    return {"council_opinions": opinions}


def check_opinions_succeeded(state: TaskState) -> str:
    """Conditional edge: check if at least one opinion succeeded."""
    opinions = state.get("council_opinions", [])
    if opinions:
        return "continue"
    return "fail"


# ---------- Stage 2: Anonymous Blind Peer Review ----------

async def review_fan_out_node(state: TaskState) -> dict:
    """Stage 2: Anonymous peer review — agents rank each other's responses."""
    task_id = state["task_id"]
    opinions = state.get("council_opinions", [])
    prompt = state["prompt"]

    await log_step(
        task_id,
        "🔍 STAGE 2: Anonymous peer review — agents ranking each other's responses...",
    )

    # Assign anonymous labels A, B, C, D... to opinions
    labels = [chr(65 + i) for i in range(len(opinions))]
    label_to_agent_id: dict[str, int] = {}
    label_to_agent_info: dict[str, dict] = {}

    for label, op in zip(labels, opinions):
        key = f"Response {label}"
        label_to_agent_id[key] = op.agent_id
        label_to_agent_info[key] = {
            "name": op.agent_name,
            "role": op.agent_role,
        }

    valid_labels = list(label_to_agent_id.keys())

    # Build anonymized response block
    anon_block = ""
    for label, op in zip(labels, opinions):
        anon_block += f"--- Response {label} ---\n{op.response}\n\n"

    step_counter = len(state.get("agents", []))

    async def review_anonymous(agent_result: AgentResult, order: int) -> AgentResult:
        role = agent_result.agent_role
        role_prompt = ROLE_SYSTEM_PROMPTS.get(role, ROLE_SYSTEM_PROMPTS["employee"])
        review_prompt = (
            f"{role_prompt}\n\n"
            f"ORIGINAL QUESTION:\n{prompt}\n\n"
            f"RESPONSES FROM THE TEAM (anonymized — you do not know who wrote what):\n\n"
            f"{anon_block}\n"
            f"Your task:\n"
            f"1. Evaluate each response individually — what it does well, what it misses.\n"
            f"2. At the end, provide your FINAL RANKING from best to worst.\n\n"
            f"IMPORTANT: End your response with EXACTLY this format:\n\n"
            f"FINAL RANKING:\n"
            f"1. Response {labels[0]}\n"
            f"2. Response {labels[1] if len(labels) > 1 else labels[0]}\n"
            f"...\n\n"
            f"Be constructive and specific in your evaluation."
        )
        # Use the agent_id from the opinion to look up agent
        agent_dict = {
            "id": agent_result.agent_id,
            "name": agent_result.agent_name,
            "role": agent_result.agent_role,
        }
        return await run_agent_step(
            task_id, agent_dict, review_prompt,
            step_order=step_counter + order, step_label="review",
        )

    # Only agents that gave opinions in Stage 1 participate in review
    review_results = await asyncio.gather(
        *[review_anonymous(op, i) for i, op in enumerate(opinions)],
        return_exceptions=True,
    )

    reviews: list[AgentResult] = []
    for i, result in enumerate(review_results):
        if isinstance(result, Exception):
            continue
        if result.status == "completed":
            reviews.append(result)

    await log_step(task_id, f"✓ Stage 2 complete — {len(reviews)} reviews collected")

    return {
        "council_reviews": reviews,
        "label_to_agent": label_to_agent_id,
    }


# ---------- Aggregate Rankings ----------

async def aggregate_rankings_node(state: TaskState) -> dict:
    """Compute aggregate rankings from peer reviews."""
    task_id = state["task_id"]
    reviews = state.get("council_reviews", [])
    label_to_agent_id = state.get("label_to_agent", {})
    opinions = state.get("council_opinions", [])

    # Build label_to_agent_info from opinions
    labels = [chr(65 + i) for i in range(len(opinions))]
    label_to_agent_info: dict[str, dict] = {}
    for label, op in zip(labels, opinions):
        key = f"Response {label}"
        label_to_agent_info[key] = {
            "name": op.agent_name,
            "role": op.agent_role,
        }

    # Convert AgentResult list to dict list for the ranking function
    review_dicts = [{"response": r.response} for r in reviews]

    aggregate = calculate_aggregate_rankings(
        review_dicts, label_to_agent_id, label_to_agent_info,
    )

    if aggregate:
        ranking_summary = " | ".join(
            f"#{i+1} {r['agent_name']} (avg {r['average_rank']})"
            for i, r in enumerate(aggregate)
        )
        await log_step(task_id, f"📊 Peer ranking results: {ranking_summary}")

    return {"council_rankings": aggregate}


# ---------- Stage 3: CEO Synthesis ----------

async def synthesis_node(state: TaskState) -> dict:
    """Stage 3: CEO synthesizes opinions, reviews, and rankings."""
    task_id = state["task_id"]
    opinions = state.get("council_opinions", [])
    reviews = state.get("council_reviews", [])
    rankings = state.get("council_rankings", [])
    agents = state.get("agents", [])

    # Find CEO agent (prefer is_orchestrator, then ceo role)
    ceo_dict = next((a for a in agents if a.get("is_orchestrator")), None)
    if not ceo_dict:
        ceo_dict = next((a for a in agents if a.get("role") == "ceo"), None)
    if not ceo_dict:
        # Fallback: use first agent
        ceo_dict = agents[0] if agents else None

    if not ceo_dict:
        return {
            "task_status": "failed",
            "final_output": "No CEO agent available for synthesis.",
        }

    ceo_name = ceo_dict.get("name", "CEO")
    await log_step(
        task_id,
        f"🧠 STAGE 3: {ceo_name} (CEO) synthesizing all opinions and reviews...",
    )

    # Build named opinions text
    opinions_text = "\n\n".join(
        f"=== {op.agent_name} ({op.agent_role.upper()}) — OPINION ===\n{op.response}"
        for op in opinions
    )

    # Build named reviews text
    reviews_text = "\n\n".join(
        f"=== {rev.agent_name} ({rev.agent_role.upper()}) — PEER REVIEW ===\n{rev.response}"
        for rev in reviews
    )

    # Build ranking context
    ranking_context = ""
    if rankings:
        ranking_context = "\n\nAGGREGATE PEER RANKINGS (from best to worst by average position):\n"
        for i, r in enumerate(rankings):
            ranking_context += (
                f"{i+1}. {r['agent_name']} ({r['agent_role'].upper()}) — "
                f"avg rank {r['average_rank']} ({r['rankings_count']} votes)\n"
            )

    step_counter = len(agents) + len(opinions)

    synthesis_prompt = (
        f"You are {ceo_name}, the CEO and leader of this AI council.\n\n"
        f"Your team was asked:\n"
        f"ORIGINAL QUESTION: {state['prompt']}\n\n"
        f"STAGE 1 — INDIVIDUAL OPINIONS:\n{opinions_text}\n\n"
        f"STAGE 2 — ANONYMOUS PEER REVIEWS:\n{reviews_text}"
        f"{ranking_context}\n\n"
        f"As CEO, synthesize all opinions and peer reviews into a single, comprehensive, actionable final answer. Consider:\n"
        f"- The strongest ideas and insights from each team member\n"
        f"- Points of agreement across the council\n"
        f"- Constructive criticisms and how they improve the final answer\n"
        f"- The peer rankings as a signal of response quality\n\n"
        f"Produce the definitive answer that represents the collective wisdom of your entire council."
    )

    synth_result = await run_agent_step(
        task_id, ceo_dict, synthesis_prompt,
        step_order=step_counter, step_label="synthesis",
    )

    if synth_result.status == "completed":
        await log_step(task_id, "✅ Council complete — CEO has produced the final answer")
        return {
            "final_output": synth_result.response,
            "task_status": "completed",
        }
    else:
        # Fallback: concatenate opinions
        fallback = "CEO synthesis failed. Individual opinions:\n\n" + "\n\n---\n\n".join(
            f"**{op.agent_name}** ({op.agent_role.upper()}):\n{op.response}"
            for op in opinions
        )
        await log_step(task_id, "CEO synthesis failed — returning raw opinions", level="error")
        return {
            "final_output": fallback,
            "task_status": "failed",
        }


# ---------- Persist Council Metadata ----------

async def persist_council_metadata_node(state: TaskState) -> dict:
    """Store council-specific metadata (rankings, label map) on the Task record."""
    task_id = state["task_id"]
    opinions = state.get("council_opinions", [])
    reviews = state.get("council_reviews", [])
    rankings = state.get("council_rankings", [])
    label_to_agent = state.get("label_to_agent", {})

    # Build valid_labels for re-parsing review rankings
    valid_labels = list(label_to_agent.keys())

    metadata = {
        "label_to_agent": label_to_agent,
        "aggregate_rankings": rankings,
        "opinions": [
            {
                "agent_id": op.agent_id,
                "agent_name": op.agent_name,
                "agent_role": op.agent_role,
                "response": op.response,
            }
            for op in opinions
        ],
        "reviews": [
            {
                "agent_id": rev.agent_id,
                "agent_name": rev.agent_name,
                "agent_role": rev.agent_role,
                "response": rev.response,
                "parsed_ranking": parse_ranking_from_text(rev.response, valid_labels),
            }
            for rev in reviews
        ],
    }

    async with async_session() as session:
        task = await session.get(Task, task_id)
        if task:
            task.task_metadata = metadata
            await session.commit()

    return {}


# ---------- Failure nodes ----------

async def council_fail_node(state: TaskState) -> dict:
    """Terminal failure — all opinions failed."""
    return {
        "task_status": "failed",
        "final_output": state.get("error", "All agents failed to provide opinions."),
    }


# ---------- Graph Builder ----------

def build_council_graph() -> StateGraph:
    """Build a LangGraph StateGraph for council deliberation (3-stage subgraph).

    Flow:
        START → opinions → [check] → reviews → rankings → synthesis → metadata → END
                                  ↘ fail → END
    """
    graph = StateGraph(TaskState)

    graph.add_node("stage1_opinions", opinion_fan_out_node)
    graph.add_node("stage2_reviews", review_fan_out_node)
    graph.add_node("aggregate_rankings", aggregate_rankings_node)
    graph.add_node("stage3_synthesis", synthesis_node)
    graph.add_node("persist_metadata", persist_council_metadata_node)
    graph.add_node("fail", council_fail_node)

    graph.add_edge(START, "stage1_opinions")
    graph.add_conditional_edges(
        "stage1_opinions",
        check_opinions_succeeded,
        {"continue": "stage2_reviews", "fail": "fail"},
    )
    graph.add_edge("stage2_reviews", "aggregate_rankings")
    graph.add_edge("aggregate_rankings", "stage3_synthesis")
    graph.add_edge("stage3_synthesis", "persist_metadata")
    graph.add_edge("persist_metadata", END)
    graph.add_edge("fail", END)

    return graph
