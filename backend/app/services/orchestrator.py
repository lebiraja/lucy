"""
Lucy Orchestrator Engine — the brain of the multi-agent system.

Supports four strategies:
  - Sequential: chain agents one after another
  - Parallel: fan-out to all agents, then aggregate
  - Dynamic: use the orchestrator agent to decide routing
  - Council: 3-stage CEO-led deliberation with anonymous peer review
"""

import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import (
    Agent, AgentState, Task, TaskStep, LogEntry,
    TaskStrategy, TaskStatus, StepStatus, LogLevel, OperationalStatus,
)
from app.services.llm_client import chat_completion
from app.services.logger import log_broadcaster


async def _log(task_id: int, message: str, level: str = "info", source: str = "orchestrator"):
    """Write a log entry to DB and broadcast via WebSocket.

    Uses its own isolated DB session — never commits or touches the caller's session.
    """
    async with async_session() as log_session:
        entry = LogEntry(
            task_id=task_id,
            level=LogLevel(level),
            source=source,
            message=message,
        )
        log_session.add(entry)
        await log_session.commit()
    await log_broadcaster.broadcast(message=message, level=level, source=source, task_id=task_id)


def _extract_json(text: str) -> str:
    """Strip markdown code fences (```json ... ``` or ``` ... ```) and return raw JSON."""
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def parse_ranking_from_text(text: str, valid_labels: list[str]) -> List[str]:
    """
    Extract ordered ranking labels from LLM output.

    Priority:
      1. FINAL RANKING: section with numbered list  → most reliable
      2. FINAL RANKING: section without numbers     → labels in order
      3. Full text scan for Response X patterns     → last resort
      4. Returns [] on complete failure
    """
    if "FINAL RANKING:" in text:
        section = text.split("FINAL RANKING:", 1)[1]
        # Primary: numbered list "1. Response A"
        numbered = re.findall(r'\d+\.\s*(Response [A-Z])', section)
        if numbered:
            return [r for r in numbered if r in valid_labels]
        # Fallback 1: any "Response X" in section order
        found = re.findall(r'Response [A-Z]', section)
        return [r for r in found if r in valid_labels]
    # Fallback 2: scan full text
    found = re.findall(r'Response [A-Z]', text)
    return [r for r in found if r in valid_labels]


def calculate_aggregate_rankings(review_results: list, label_to_agent: dict) -> list:
    """
    Aggregate peer rankings into a leaderboard.
    Average rank position per agent (1 = best). Lower average = better.
    """
    valid_labels = list(label_to_agent.keys())
    agent_positions: dict[int, list[int]] = defaultdict(list)

    for review in review_results:
        parsed = parse_ranking_from_text(review["response"], valid_labels)
        for position, label in enumerate(parsed, start=1):
            agent = label_to_agent.get(label)
            if agent:
                agent_positions[agent.id].append(position)

    aggregate = []
    for label, agent in label_to_agent.items():
        positions = agent_positions.get(agent.id, [])
        if positions:
            aggregate.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_role": agent.role.value,
                "average_rank": round(sum(positions) / len(positions), 2),
                "rankings_count": len(positions),
                "label": label,
            })

    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def _run_step(
    task_id: int,
    agent: Agent,
    prompt: str,
    step_order: int,
    step_label: str | None = None,
) -> dict:
    """Execute a single step using an isolated database session to allow safe concurrent execution."""
    async with async_session() as step_session:
        step = TaskStep(
            task_id=task_id,
            agent_id=agent.id,
            step_order=step_order,
            input_prompt=prompt,
            status=StepStatus.RUNNING,
            step_label=step_label,
        )
        step_session.add(step)

        # Mark agent as executing
        local_agent = await step_session.get(Agent, agent.id)
        if local_agent:
            local_agent.state = AgentState.EXECUTING
            local_agent.last_heartbeat = datetime.now(timezone.utc)

        await step_session.commit()

        await _log(task_id, f"Sending prompt to [{agent.name}] ({agent.model_name or 'auto'})...", source=agent.name)

        try:
            # Re-fetch step after commit to get its id
            await step_session.refresh(step)
            response_text, duration_ms = await chat_completion(
                agent=local_agent or agent,
                messages=[{"role": "user", "content": prompt}],
            )

            step.response = response_text
            step.duration_ms = duration_ms
            step.status = StepStatus.COMPLETED

            # Update agent metrics
            if local_agent:
                local_agent.state = AgentState.IDLE
                # Exponential moving average of response time
                if local_agent.avg_response_time_ms is not None:
                    local_agent.avg_response_time_ms = round(
                        local_agent.avg_response_time_ms * 0.8 + duration_ms * 0.2, 1
                    )
                else:
                    local_agent.avg_response_time_ms = float(duration_ms)

            await step_session.commit()

            await _log(
                task_id,
                f"[{agent.name}] responded in {duration_ms}ms ({len(response_text)} chars)",
                source=agent.name, level="agent",
            )
            return {"status": StepStatus.COMPLETED, "response": response_text, "duration_ms": duration_ms}

        except Exception as e:
            step.status = StepStatus.FAILED
            step.response = f"ERROR: {str(e)}"

            if local_agent:
                local_agent.state = AgentState.FAILED
                local_agent.crash_count = (local_agent.crash_count or 0) + 1

            await step_session.commit()

            await _log(task_id, f"[{agent.name}] FAILED: {str(e)}", source=agent.name, level="error")
            return {"status": StepStatus.FAILED, "response": f"ERROR: {str(e)}", "duration_ms": 0}


async def execute_sequential(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Sequential strategy: Chain agents one after another.
    Each agent receives the original prompt + all previous responses.
    """
    await _log(task.id, f"Starting SEQUENTIAL execution with {len(agents)} agents")

    accumulated = task.prompt
    final_response = ""

    for i, agent in enumerate(agents):
        step_result = await _run_step(task.id, agent, accumulated, step_order=i)

        if step_result["status"] == StepStatus.FAILED:
            await _log(task.id, f"Sequential chain broken at step {i + 1} ({agent.name})", level="error")
            task.status = TaskStatus.FAILED
            task.final_output = f"Chain failed at step {i + 1} ({agent.name}): {step_result['response']}"
            return

        final_response = step_result["response"]
        # Build context for next agent
        accumulated = (
            f"Original prompt: {task.prompt}\n\n"
            f"Previous agent ({agent.name}) responded:\n{step_result['response']}\n\n"
            f"Please continue building on this response."
        )

    task.status = TaskStatus.COMPLETED
    task.final_output = final_response
    task.completed_at = datetime.now(timezone.utc)
    await _log(task.id, "Sequential execution completed successfully")


async def execute_parallel(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Parallel strategy: Fan-out the prompt to all agents simultaneously,
    then use the orchestrator agent (if available) to synthesize responses.
    """
    await _log(task.id, f"Starting PARALLEL execution with {len(agents)} agents")

    # Fan-out to all agents concurrently
    async def run_agent(agent, order):
        return await _run_step(task.id, agent, task.prompt, step_order=order)

    steps = await asyncio.gather(*[run_agent(agent, i) for i, agent in enumerate(agents)], return_exceptions=True)

    # Collect successful responses
    responses = []
    for i, step_result in enumerate(steps):
        if isinstance(step_result, Exception):
            await _log(task.id, f"Agent {agents[i].name} raised exception: {step_result}", level="error")
            continue
        if step_result["status"] == StepStatus.COMPLETED:
            responses.append({
                "agent": agents[i].name,
                "model": agents[i].model_name or "unknown",
                "role": agents[i].role,
                "response": step_result["response"],
            })

    if not responses:
        task.status = TaskStatus.FAILED
        task.final_output = "All agents failed to respond."
        await _log(task.id, "All agents failed — no responses to aggregate", level="error")
        return

    await _log(task.id, f"Collected {len(responses)} responses, aggregating...")

    # Find orchestrator agent for synthesis (fresh session avoids stale connection on long tasks)
    orchestrator_agent = None
    async with async_session() as orch_session:
        orch_result = await orch_session.execute(
            select(Agent).where(
                Agent.is_orchestrator == True,
                Agent.is_active == True,
                Agent.operational_status == OperationalStatus.ACTIVE,
            )
        )
        orchestrator_agent = orch_result.scalar_one_or_none()

    if orchestrator_agent:
        synthesis_prompt = (
            f"You are Lucy, the orchestrator agent. Multiple AI agents were asked the following question:\n\n"
            f"ORIGINAL PROMPT: {task.prompt}\n\n"
            f"Here are their responses:\n\n"
        )
        for r in responses:
            synthesis_prompt += f"--- {r['agent']} ({r['model']}, role: {r['role']}) ---\n{r['response']}\n\n"
        synthesis_prompt += (
            "Please synthesize these responses into a single, comprehensive, high-quality answer. "
            "Take the best parts from each response, resolve any contradictions, and produce the definitive answer."
        )
        synth_step = await _run_step(task.id, orchestrator_agent, synthesis_prompt, step_order=len(agents))
        if synth_step["status"] == StepStatus.COMPLETED:
            task.final_output = synth_step["response"]
        else:
            task.final_output = "\n\n---\n\n".join(
                f"**{r['agent']}** ({r['model']}):\n{r['response']}" for r in responses
            )
    else:
        task.final_output = "\n\n---\n\n".join(
            f"**{r['agent']}** ({r['model']}):\n{r['response']}" for r in responses
        )

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    await _log(task.id, "Parallel execution completed successfully")


async def execute_dynamic(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Dynamic strategy: Ask the orchestrator agent to analyze the prompt and
    decide which agents to route to and in what order.
    """
    await _log(task.id, "Starting DYNAMIC execution — consulting orchestrator...")

    # Find orchestrator (fresh session avoids stale connection on long tasks)
    async with async_session() as orch_session:
        orch_result = await orch_session.execute(
            select(Agent).where(
                Agent.is_orchestrator == True,
                Agent.is_active == True,
                Agent.operational_status == OperationalStatus.ACTIVE,
            )
        )
        orchestrator_agent = orch_result.scalar_one_or_none()

    if not orchestrator_agent:
        await _log(task.id, "No orchestrator agent configured — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    # Build agent catalog for the orchestrator
    agent_catalog = [
        {
            "id": a.id,
            "name": a.name,
            "model": a.model_name or "unknown",
            "role": a.role,
            "description": a.description or "No description",
        }
        for a in agents if a.id != orchestrator_agent.id
    ]

    routing_prompt = (
        f"You are Lucy, the orchestrator of a multi-agent AI system. "
        f"You must decide how to handle the following user query by routing it to the appropriate agents.\n\n"
        f"USER QUERY: {task.prompt}\n\n"
        f"AVAILABLE AGENTS:\n{json.dumps(agent_catalog, indent=2)}\n\n"
        f"Respond with a JSON object with this exact structure:\n"
        f'{{"strategy": "sequential" or "parallel", "agent_ids": [list of agent IDs in order], "reasoning": "brief explanation"}}\n\n'
        f"Only respond with the JSON object, nothing else."
    )

    routing_step = await _run_step(task.id, orchestrator_agent, routing_prompt, step_order=0)

    if routing_step["status"] == StepStatus.FAILED:
        await _log(task.id, "Orchestrator failed to route — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    try:
        response_text = _extract_json(routing_step["response"])
        decision = json.loads(response_text)
        selected_ids = decision.get("agent_ids", [])
        sub_strategy = decision.get("strategy", "parallel")
        reasoning = decision.get("reasoning", "No reasoning provided")

        await _log(task.id, f"Orchestrator decided: {sub_strategy} with agents {selected_ids}. Reasoning: {reasoning}")

        selected_agents = [a for a in agents if a.id in selected_ids]
        if not selected_agents:
            await _log(task.id, "No valid agents selected — using all agents", level="warning")
            selected_agents = [a for a in agents if a.id != orchestrator_agent.id]

        if sub_strategy == "sequential":
            await execute_sequential(session, task, selected_agents)
        else:
            await execute_parallel(session, task, selected_agents)

    except (json.JSONDecodeError, KeyError) as e:
        await _log(
            task.id,
            f"Failed to parse orchestrator routing decision: {e}. Raw response: {routing_step['response'][:200]}. Falling back to parallel.",
            level="warning",
        )
        non_orch_agents = [a for a in agents if a.id != orchestrator_agent.id]
        await execute_parallel(session, task, non_orch_agents)



# ---------- Role-aware prompts for council ----------

ROLE_SYSTEM_PROMPTS = {
    "ceo": (
        "You are a CEO-level strategic AI. Analyze from a high-level business and strategic perspective. "
        "Focus on vision, priorities, risks, resource allocation, and overall direction."
    ),
    "cto": (
        "You are a CTO-level technical AI. Analyze from a deep technical perspective. "
        "Focus on architecture, technology choices, scalability, security, and engineering trade-offs."
    ),
    "manager": (
        "You are a Manager-level AI responsible for execution. Analyze from an implementation perspective. "
        "Focus on timelines, team capacity, milestones, dependencies, and practical execution steps."
    ),
    "employee": (
        "You are a specialist AI contributor. Provide detailed, hands-on analysis. "
        "Focus on specifics, implementation details, and ground-level insights."
    ),
}


async def execute_council(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Council strategy: 3-stage CEO-led deliberation with anonymous peer review.

    Stage 1 — Individual opinions (parallel, role-aware prompts)
    Stage 2 — Anonymous blind peer review + structured ranking (parallel)
    Stage 3 — CEO/Chairman synthesis with full named context
    """
    # Find CEO (prefer is_orchestrator flag, then ceo role)
    ceo_agent = next((a for a in agents if a.is_orchestrator), None)
    if not ceo_agent:
        ceo_agent = next((a for a in agents if a.role.value == "ceo"), None)
    if not ceo_agent:
        await _log(task.id, "No CEO/orchestrator found — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    step_counter = 0

    # =========================================================
    # STAGE 1 — Individual Opinions (parallel, role-aware)
    # =========================================================
    await _log(task.id, "📋 STAGE 1: Collecting individual opinions from all agents...")

    async def get_opinion(agent, order):
        role_prompt = ROLE_SYSTEM_PROMPTS.get(agent.role.value, ROLE_SYSTEM_PROMPTS["employee"])
        prompt = (
            f"{role_prompt}\n\n"
            f"You are {agent.name} (Role: {agent.role.value.upper()}).\n\n"
            f"Please provide your expert analysis of the following:\n\n"
            f"{task.prompt}"
        )
        return await _run_step(task.id, agent, prompt, step_order=order, step_label="opinion")

    opinion_steps = await asyncio.gather(
        *[get_opinion(a, i) for i, a in enumerate(agents)],
        return_exceptions=True,
    )
    step_counter = len(agents)

    # Collect only successful opinions
    opinions = []
    for i, result in enumerate(opinion_steps):
        if isinstance(result, Exception):
            await _log(task.id, f"Agent {agents[i].name} failed in Stage 1: {result}", level="error")
            continue
        if result["status"] == StepStatus.COMPLETED:
            opinions.append({"agent": agents[i], "response": result["response"]})

    if not opinions:
        task.status = TaskStatus.FAILED
        task.final_output = "All agents failed to provide opinions."
        await _log(task.id, "Stage 1 failed — no responses", level="error")
        return

    await _log(task.id, f"✓ Stage 1 complete — {len(opinions)} opinions collected")

    # =========================================================
    # STAGE 2 — Anonymous Blind Peer Review (parallel)
    # Responses get A/B/C/D labels — agents don't know who wrote what.
    # Each agent must provide a FINAL RANKING: section.
    # =========================================================
    await _log(task.id, "🔍 STAGE 2: Anonymous peer review — agents ranking each other's responses...")

    # Assign labels A, B, C, D... to opinions
    labels = [chr(65 + i) for i in range(len(opinions))]
    label_to_agent: dict[str, Agent] = {
        f"Response {label}": op["agent"]
        for label, op in zip(labels, opinions)
    }
    valid_labels = list(label_to_agent.keys())

    # Build anonymized response block shown to ALL reviewers
    anon_block = ""
    for label, op in zip(labels, opinions):
        anon_block += f"--- Response {label} ---\n{op['response']}\n\n"

    async def review_anonymous(reviewing_agent, order):
        role_prompt = ROLE_SYSTEM_PROMPTS.get(reviewing_agent.role.value, ROLE_SYSTEM_PROMPTS["employee"])
        prompt = (
            f"{role_prompt}\n\n"
            f"ORIGINAL QUESTION:\n{task.prompt}\n\n"
            f"RESPONSES FROM THE TEAM (anonymized — you do not know who wrote what):\n\n"
            f"{anon_block}\n"
            f"Your task:\n"
            f"1. Evaluate each response individually — what it does well, what it misses.\n"
            f"2. At the end, provide your FINAL RANKING from best to worst.\n\n"
            f"IMPORTANT: End your response with EXACTLY this format (no extra text in the ranking section):\n\n"
            f"FINAL RANKING:\n"
            f"1. Response {labels[0]}\n"
            f"2. Response {labels[1] if len(labels) > 1 else labels[0]}\n"
            f"...\n\n"
            f"Be constructive and specific in your evaluation."
        )
        return await _run_step(task.id, reviewing_agent, prompt, step_order=order, step_label="review")

    # Only agents that gave opinions in Stage 1 participate in Stage 2
    reviewing_agents = [op["agent"] for op in opinions]
    review_steps = await asyncio.gather(
        *[review_anonymous(a, step_counter + i) for i, a in enumerate(reviewing_agents)],
        return_exceptions=True,
    )
    step_counter += len(reviewing_agents)

    # Collect successful reviews
    reviews = []
    for i, result in enumerate(review_steps):
        if isinstance(result, Exception):
            continue
        if result["status"] == StepStatus.COMPLETED:
            reviews.append({"agent": reviewing_agents[i], "response": result["response"]})

    await _log(task.id, f"✓ Stage 2 complete — {len(reviews)} reviews collected")

    # Calculate aggregate rankings across all reviewers
    aggregate_rankings = calculate_aggregate_rankings(reviews, label_to_agent)
    if aggregate_rankings:
        ranking_summary = " | ".join(
            f"#{i+1} {r['agent_name']} (avg {r['average_rank']})"
            for i, r in enumerate(aggregate_rankings)
        )
        await _log(task.id, f"📊 Peer ranking results: {ranking_summary}")

    # =========================================================
    # STAGE 3 — CEO Synthesis (single, receives full named context)
    # =========================================================
    await _log(task.id, f"🧠 STAGE 3: {ceo_agent.name} (CEO) synthesizing all opinions and reviews...")

    opinions_text = "\n\n".join(
        f"=== {op['agent'].name} ({op['agent'].role.value.upper()}) — OPINION ===\n{op['response']}"
        for op in opinions
    )
    reviews_text = "\n\n".join(
        f"=== {rev['agent'].name} ({rev['agent'].role.value.upper()}) — PEER REVIEW ===\n{rev['response']}"
        for rev in reviews
    )
    ranking_context = ""
    if aggregate_rankings:
        ranking_context = "\n\nAGGREGATE PEER RANKINGS (from best to worst by average position):\n"
        for i, r in enumerate(aggregate_rankings):
            ranking_context += f"{i+1}. {r['agent_name']} ({r['agent_role'].upper()}) — avg rank {r['average_rank']} ({r['rankings_count']} votes)\n"

    synthesis_prompt = (
        f"You are {ceo_agent.name}, the CEO and leader of this AI council.\n\n"
        f"Your team was asked:\n"
        f"ORIGINAL QUESTION: {task.prompt}\n\n"
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

    synth_step = await _run_step(
        task.id, ceo_agent, synthesis_prompt, step_order=step_counter, step_label="synthesis"
    )

    if synth_step["status"] == StepStatus.COMPLETED:
        task.final_output = synth_step["response"]
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        # Store council metadata for frontend display
        task.task_metadata = {
            "label_to_agent": {label: a.id for label, a in label_to_agent.items()},
            "aggregate_rankings": aggregate_rankings,
            "opinions": [
                {"agent_id": op["agent"].id, "agent_name": op["agent"].name,
                 "agent_role": op["agent"].role.value, "response": op["response"]}
                for op in opinions
            ],
            "reviews": [
                {"agent_id": rev["agent"].id, "agent_name": rev["agent"].name,
                 "agent_role": rev["agent"].role.value, "response": rev["response"],
                 "parsed_ranking": parse_ranking_from_text(rev["response"], valid_labels)}
                for rev in reviews
            ],
        }
        await _log(task.id, "✅ Council complete — CEO has produced the final answer")
    else:
        # Fallback: concatenate all opinions
        task.final_output = "CEO synthesis failed. Individual opinions:\n\n" + "\n\n---\n\n".join(
            f"**{op['agent'].name}** ({op['agent'].role.value.upper()}):\n{op['response']}"
            for op in opinions
        )
        task.status = TaskStatus.FAILED
        await _log(task.id, "CEO synthesis failed — returning raw opinions", level="error")


async def execute_task(session: AsyncSession, task: Task, agents: list[Agent]):
    """Main entry point — dispatch to the correct strategy."""
    task.status = TaskStatus.RUNNING
    await session.flush()

    await _log(task.id, f"Task #{task.id} started — strategy: {task.strategy.value}")

    try:
        if task.strategy == TaskStrategy.SEQUENTIAL:
            await execute_sequential(session, task, agents)
        elif task.strategy == TaskStrategy.PARALLEL:
            await execute_parallel(session, task, agents)
        elif task.strategy == TaskStrategy.DYNAMIC:
            await execute_dynamic(session, task, agents)
        elif task.strategy == TaskStrategy.COUNCIL:
            await execute_council(session, task, agents)
        else:
            task.status = TaskStatus.FAILED
            task.final_output = f"Unknown strategy: {task.strategy}"
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.final_output = f"Orchestration error: {str(e)}"
        await _log(task.id, f"Orchestration error: {str(e)}", level="error")

    await session.flush()
    await _log(task.id, f"Task #{task.id} finished — status: {task.status.value}")
