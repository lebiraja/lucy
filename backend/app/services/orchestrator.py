"""
Lucy Orchestrator Engine — the brain of the multi-agent system.

Supports three strategies:
  - Sequential: chain agents one after another
  - Parallel: fan-out to all agents, then aggregate
  - Dynamic: use the orchestrator agent to decide routing
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import Agent, Task, TaskStep, LogEntry, TaskStrategy, TaskStatus, StepStatus, LogLevel
from app.services.llm_client import chat_completion
from app.services.logger import log_broadcaster


async def _log(session: AsyncSession, task_id: int, message: str, level: str = "info", source: str = "orchestrator"):
    """Write a log entry to DB and broadcast via WebSocket."""
    entry = LogEntry(
        task_id=task_id,
        level=LogLevel(level),
        source=source,
        message=message,
    )
    session.add(entry)
    await session.commit()
    await log_broadcaster.broadcast(message=message, level=level, source=source, task_id=task_id)


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
        await step_session.commit()

        await _log(step_session, task_id, f"Sending prompt to [{agent.name}] ({agent.model_name or 'auto'})...", source=agent.name)

        try:
            # Re-fetch agent in this session for the LLM call to avoid DetachedInstanceError limits
            local_agent = await step_session.get(Agent, agent.id)
            response_text, duration_ms = await chat_completion(
                agent=local_agent,
                messages=[{"role": "user", "content": prompt}],
            )
            
            step.response = response_text
            step.duration_ms = duration_ms
            step.status = StepStatus.COMPLETED
            await step_session.commit()
            
            await _log(
                step_session, task_id,
                f"[{agent.name}] responded in {duration_ms}ms ({len(response_text)} chars)",
                source=agent.name, level="agent",
            )
            return {"status": StepStatus.COMPLETED, "response": response_text, "duration_ms": duration_ms}
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.response = f"ERROR: {str(e)}"
            await step_session.commit()
            
            await _log(step_session, task_id, f"[{agent.name}] FAILED: {str(e)}", source=agent.name, level="error")
            return {"status": StepStatus.FAILED, "response": f"ERROR: {str(e)}", "duration_ms": 0}


async def execute_sequential(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Sequential strategy: Chain agents one after another.
    Each agent receives the original prompt + all previous responses.
    """
    await _log(session, task.id, f"Starting SEQUENTIAL execution with {len(agents)} agents")

    accumulated = task.prompt
    final_response = ""

    for i, agent in enumerate(agents):
        step_result = await _run_step(task.id, agent, accumulated, step_order=i)

        if step_result["status"] == StepStatus.FAILED:
            await _log(session, task.id, f"Sequential chain broken at step {i + 1} ({agent.name})", level="error")
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
    await _log(session, task.id, "Sequential execution completed successfully")


async def execute_parallel(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Parallel strategy: Fan-out the prompt to all agents simultaneously,
    then use the orchestrator agent (if available) to synthesize responses.
    """
    await _log(session, task.id, f"Starting PARALLEL execution with {len(agents)} agents")

    # Fan-out to all agents concurrently
    async def run_agent(agent, order):
        return await _run_step(task.id, agent, task.prompt, step_order=order)

    tasks_coros = [run_agent(agent, i) for i, agent in enumerate(agents)]
    steps = await asyncio.gather(*tasks_coros, return_exceptions=True)

    # Collect successful responses
    responses = []
    for i, step_result in enumerate(steps):
        if isinstance(step_result, Exception):
            await _log(session, task.id, f"Agent {agents[i].name} raised exception: {step_result}", level="error")
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
        await _log(session, task.id, "All agents failed — no responses to aggregate", level="error")
        return

    await _log(session, task.id, f"Collected {len(responses)} responses, aggregating...")

    # Find orchestrator agent for synthesis
    orchestrator = await session.execute(
        select(Agent).where(Agent.is_orchestrator == True, Agent.is_active == True)
    )
    orchestrator_agent = orchestrator.scalar_one_or_none()

    if orchestrator_agent:
        # Use orchestrator to synthesize
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

        synth_step = await _run_step(
            task.id, orchestrator_agent, synthesis_prompt, step_order=len(agents)
        )

        if synth_step["status"] == StepStatus.COMPLETED:
            task.final_output = synth_step["response"]
        else:
            # Fallback: concatenate all responses
            task.final_output = "\n\n---\n\n".join(
                f"**{r['agent']}** ({r['model']}):\n{r['response']}" for r in responses
            )
    else:
        # No orchestrator — return all responses
        task.final_output = "\n\n---\n\n".join(
            f"**{r['agent']}** ({r['model']}):\n{r['response']}" for r in responses
        )

    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    await _log(session, task.id, "Parallel execution completed successfully")


async def execute_dynamic(session: AsyncSession, task: Task, agents: list[Agent]):
    """
    Dynamic strategy: Ask the orchestrator agent to analyze the prompt and
    decide which agents to route to and in what order.
    """
    await _log(session, task.id, "Starting DYNAMIC execution — consulting orchestrator...")

    # Find orchestrator
    result = await session.execute(
        select(Agent).where(Agent.is_orchestrator == True, Agent.is_active == True)
    )
    orchestrator_agent = result.scalar_one_or_none()

    if not orchestrator_agent:
        await _log(session, task.id, "No orchestrator agent configured — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    # Build agent catalog for the orchestrator
    agent_catalog = []
    for a in agents:
        if a.id != orchestrator_agent.id:
            agent_catalog.append({
                "id": a.id,
                "name": a.name,
                "model": a.model_name or "unknown",
                "role": a.role,
                "description": a.description or "No description",
            })

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
        await _log(session, task.id, "Orchestrator failed to route — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    # Parse routing decision
    try:
        # Try to extract JSON from the response
        response_text = routing_step["response"].strip()
        # Handle markdown code block wrapping
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        decision = json.loads(response_text)
        selected_ids = decision.get("agent_ids", [])
        sub_strategy = decision.get("strategy", "parallel")
        reasoning = decision.get("reasoning", "No reasoning provided")

        await _log(session, task.id, f"Orchestrator decided: {sub_strategy} with agents {selected_ids}. Reasoning: {reasoning}")

        # Get selected agents
        selected_agents = [a for a in agents if a.id in selected_ids]
        if not selected_agents:
            await _log(session, task.id, "No valid agents selected — using all agents", level="warning")
            selected_agents = [a for a in agents if a.id != orchestrator_agent.id]

        # Execute with the decided sub-strategy
        if sub_strategy == "sequential":
            await execute_sequential(session, task, selected_agents)
        else:
            await execute_parallel(session, task, selected_agents)

    except (json.JSONDecodeError, KeyError) as e:
        await _log(
            session, task.id,
            f"Failed to parse orchestrator routing decision: {e}. Falling back to parallel.",
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
    Council strategy: 4-stage CEO-led hierarchical discussion.

    Stage 1 — Individual opinions (parallel, role-aware)
    Stage 2 — Cross-review & debate (parallel)
    Stage 3 — CEO synthesis (single)
    Stage 4 — Final plan output
    """
    # Find CEO (orchestrator)
    ceo_agent = next((a for a in agents if a.is_orchestrator), None)
    if not ceo_agent:
        ceo_agent = next((a for a in agents if a.role.value == "ceo"), None)
    if not ceo_agent:
        await _log(session, task.id, "No CEO/orchestrator found — falling back to parallel", level="warning")
        return await execute_parallel(session, task, agents)

    all_agents = agents
    step_counter = 0

    # =========================================================
    # STAGE 1 — Individual Opinions (parallel, role-aware)
    # =========================================================
    await _log(session, task.id, "📋 STAGE 1: Collecting individual opinions from all agents...")

    async def get_opinion(agent, order):
        role_prompt = ROLE_SYSTEM_PROMPTS.get(agent.role.value, ROLE_SYSTEM_PROMPTS["employee"])
        prompt = (
            f"{role_prompt}\n\n"
            f"You are {agent.name} (Role: {agent.role.value.upper()}).\n\n"
            f"Please provide your expert analysis of the following:\n\n"
            f"{task.prompt}"
        )
        return await _run_step(task.id, agent, prompt, step_order=order, step_label="opinion")

    opinion_coros = [get_opinion(agent, i) for i, agent in enumerate(all_agents)]
    opinion_steps = await asyncio.gather(*opinion_coros, return_exceptions=True)
    step_counter = len(all_agents)

    # Collect successful opinions
    opinions = []
    for i, step_dict in enumerate(opinion_steps):
        if isinstance(step_dict, Exception):
            await _log(session, task.id, f"Agent {all_agents[i].name} failed in Stage 1: {step_dict}", level="error")
            continue
        if step_dict["status"] == StepStatus.COMPLETED:
            opinions.append({
                "agent": all_agents[i],
                "response": step_dict["response"],
            })

    if not opinions:
        task.status = TaskStatus.FAILED
        task.final_output = "All agents failed to provide opinions."
        await _log(session, task.id, "Stage 1 failed — no responses", level="error")
        return

    await _log(session, task.id, f"✓ Stage 1 complete — {len(opinions)} opinions collected")

    # =========================================================
    # STAGE 2 — Cross-Review & Debate (parallel)
    # =========================================================
    await _log(session, task.id, "🔍 STAGE 2: Cross-review — agents evaluating each other's responses...")

    async def review_others(agent, order):
        # Build context of all OTHER agents' opinions
        others_text = ""
        for op in opinions:
            if op["agent"].id != agent.id:
                others_text += (
                    f"--- {op['agent'].name} ({op['agent'].role.value.upper()}) ---\n"
                    f"{op['response']}\n\n"
                )

        # Also include this agent's own opinion for reference
        own_opinion = next((op["response"] for op in opinions if op["agent"].id == agent.id), "")

        prompt = (
            f"You are {agent.name} (Role: {agent.role.value.upper()}).\n\n"
            f"ORIGINAL QUESTION:\n{task.prompt}\n\n"
            f"YOUR PREVIOUS RESPONSE:\n{own_opinion}\n\n"
            f"OTHER TEAM MEMBERS' RESPONSES:\n{others_text}\n"
            f"Please review your teammates' responses:\n"
            f"1. What do you agree with? What are the strongest points?\n"
            f"2. What do you disagree with or think is missing?\n"
            f"3. What improvements or additions would you suggest?\n"
            f"4. Any risks or concerns the team should consider?\n\n"
            f"Be constructive and specific. This is a team discussion."
        )
        return await _run_step(task.id, agent, prompt, step_order=order, step_label="review")

    review_coros = [review_others(agent, step_counter + i) for i, agent in enumerate(all_agents)]
    review_steps = await asyncio.gather(*review_coros, return_exceptions=True)
    step_counter += len(all_agents)

    # Collect successful reviews
    reviews = []
    for i, step_dict in enumerate(review_steps):
        if isinstance(step_dict, Exception):
            continue
        if step_dict["status"] == StepStatus.COMPLETED:
            reviews.append({
                "agent": all_agents[i],
                "response": step_dict["response"],
            })

    await _log(session, task.id, f"✓ Stage 2 complete — {len(reviews)} reviews collected")

    # =========================================================
    # STAGE 3 — CEO Synthesis
    # =========================================================
    await _log(session, task.id, "🧠 STAGE 3: CEO synthesizing all opinions and reviews into final plan...")

    # Build comprehensive context for CEO
    opinions_text = "\n\n".join([
        f"=== {op['agent'].name} ({op['agent'].role.value.upper()}) — OPINION ===\n{op['response']}"
        for op in opinions
    ])

    reviews_text = "\n\n".join([
        f"=== {rev['agent'].name} ({rev['agent'].role.value.upper()}) — REVIEW ===\n{rev['response']}"
        for rev in reviews
    ])

    synthesis_prompt = (
        f"You are {ceo_agent.name}, the CEO and leader of this AI team.\n\n"
        f"Your team has been asked the following question:\n"
        f"ORIGINAL QUESTION: {task.prompt}\n\n"
        f"STAGE 1 — INDIVIDUAL OPINIONS:\n{opinions_text}\n\n"
        f"STAGE 2 — CROSS-REVIEWS & DEBATE:\n{reviews_text}\n\n"
        f"As the CEO, synthesize all the opinions and reviews into a single, comprehensive, "
        f"actionable final plan. Consider:\n"
        f"- The strongest ideas from each team member\n"
        f"- Points of agreement across the team\n"
        f"- Constructive criticisms and how to address them\n"
        f"- A clear, structured plan with priorities\n\n"
        f"Produce the definitive team answer that represents the collective wisdom of your entire team."
    )

    synth_step = await _run_step(
        task.id, ceo_agent, synthesis_prompt, step_order=step_counter, step_label="synthesis"
    )

    # =========================================================
    # STAGE 4 — Final Output
    # =========================================================
    if synth_step["status"] == StepStatus.COMPLETED:
        task.final_output = synth_step["response"]
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        await _log(session, task.id, "✅ Council discussion complete — CEO has produced the final plan")
    else:
        # Fallback: concatenate all opinions
        task.final_output = "CEO synthesis failed. Individual opinions:\n\n" + "\n\n---\n\n".join(
            f"**{op['agent'].name}** ({op['agent'].role.value.upper()}):\n{op['response']}" for op in opinions
        )
        task.status = TaskStatus.FAILED
        await _log(session, task.id, "CEO synthesis failed — returning raw opinions", level="error")


async def execute_task(session: AsyncSession, task: Task, agents: list[Agent]):
    """Main entry point — dispatch to the correct strategy."""
    task.status = TaskStatus.RUNNING
    await session.flush()

    await _log(session, task.id, f"Task #{task.id} started — strategy: {task.strategy.value}")

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
        await _log(session, task.id, f"Orchestration error: {str(e)}", level="error")

    await session.flush()
    await _log(session, task.id, f"Task #{task.id} finished — status: {task.status.value}")
