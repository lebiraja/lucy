"""Agent execution nodes — core workhorses of the LangGraph engine.

Includes agentic tool-use loop: agents can call tools mid-response,
receive results, and continue reasoning until they produce a final answer.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.database import async_session
from app.models import Agent, AgentState, TaskStep, StepStatus
from app.services.llm_client import chat_completion
from app.services.langgraph.state import TaskState, AgentResult
from app.services.langgraph.nodes.utility_nodes import log_step
from app.services.tools import TOOL_PERMISSIONS, get_tool_prompt, execute_tool


# ---------- Role-aware system prompts ----------

ROLE_SYSTEM_PROMPTS = {
    "ceo": (
        "You are a CEO-level strategic AI. Analyze from a high-level business and strategic perspective. "
        "Focus on vision, priorities, risks, resource allocation, and overall direction."
    ),
    "cto": (
        "You are a CTO-level technical AI. Analyze from a deep technical perspective. "
        "Focus on architecture, technology choices, scalability, security, and engineering trade-offs."
    ),
    "cfo": (
        "You are a CFO-level financial AI. Analyze from a financial and business perspective. "
        "Focus on costs, budgets, ROI, financial risks, and resource efficiency."
    ),
    "manager": (
        "You are a Manager-level AI responsible for execution. Analyze from an implementation perspective. "
        "Focus on timelines, team capacity, milestones, dependencies, and practical execution steps."
    ),
    "developer": (
        "You are a Senior Developer AI. Provide precise, working code and technical solutions. "
        "Focus on correctness, best practices, performance, and maintainability."
    ),
    "tester": (
        "You are a QA Engineer AI. Focus on test coverage, edge cases, bugs, and quality assurance. "
        "Write test cases and identify potential failure points."
    ),
    "employee": (
        "You are a specialist AI contributor. Provide detailed, hands-on analysis. "
        "Focus on specifics, implementation details, and ground-level insights."
    ),
}


# ---------- Tool call parsing ----------

_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


def _extract_tool_call(text: str) -> dict | None:
    """Parse the first <tool_call>...</tool_call> block from LLM output."""
    match = _TOOL_CALL_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


def _strip_tool_call(text: str) -> str:
    """Remove tool_call tags from text."""
    return _TOOL_CALL_RE.sub("", text).strip()


# ---------- Core agent step runner with agentic loop ----------

async def run_agent_step(
    task_id: int,
    agent_dict: dict,
    prompt: str,
    step_order: int,
    step_label: str | None = None,
    workspace_dir: str | None = None,
    conversation_history: list[dict] | None = None,
) -> AgentResult:
    """Execute a single agent step with tool-use agentic loop.

    Flow:
      1. Build messages (system prompt + tool instructions + conversation history + user prompt)
      2. Call LLM
      3. If response contains <tool_call>: execute tool, append result, re-call LLM
      4. Repeat up to max_tool_iterations
      5. Return final text response + accumulated tool calls
    """
    settings = get_settings()

    async with async_session() as session:
        agent = await session.get(Agent, agent_dict["id"])
        if not agent:
            return AgentResult(
                agent_id=agent_dict["id"],
                agent_name=agent_dict.get("name", "unknown"),
                agent_role=agent_dict.get("role", "employee"),
                model_name="unknown",
                response="Agent not found in database",
                duration_ms=0,
                status="failed",
                step_label=step_label,
            )

        step = TaskStep(
            task_id=task_id,
            agent_id=agent.id,
            step_order=step_order,
            input_prompt=prompt,
            status=StepStatus.RUNNING,
            step_label=step_label,
        )
        session.add(step)
        agent.state = AgentState.EXECUTING
        agent.last_heartbeat = datetime.now(timezone.utc)
        await session.commit()

        role = agent.role.value
        tool_prompt = get_tool_prompt(role)
        role_system = ROLE_SYSTEM_PROMPTS.get(role, ROLE_SYSTEM_PROMPTS["employee"])
        system_content = role_system + tool_prompt

        # Build message list: system + past conversation + current prompt
        messages: list[dict] = [{"role": "system", "content": system_content}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        await log_step(
            task_id,
            f"[{agent.name}] starting ({agent.model_name or 'auto'}) with {len(TOOL_PERMISSIONS.get(role, []))} tools available",
            source=agent.name,
        )

        accumulated_tool_calls: list[dict] = []
        total_duration_ms = 0
        final_response = ""

        try:
            await session.refresh(step)

            for iteration in range(settings.max_tool_iterations + 1):
                iter_start = time.monotonic()
                response_text, duration_ms = await chat_completion(
                    agent=agent,
                    messages=messages,
                )
                total_duration_ms += duration_ms

                tool_call = _extract_tool_call(response_text)

                if tool_call is None or iteration == settings.max_tool_iterations:
                    # No more tool calls — this is the final answer
                    final_response = _strip_tool_call(response_text)
                    break

                # Execute the tool
                tool_name = tool_call.get("tool", "")
                tool_args = tool_call.get("args", {})
                allowed_tools = TOOL_PERMISSIONS.get(role, [])

                if tool_name not in allowed_tools:
                    tool_result = {"error": f"Tool '{tool_name}' not permitted for role '{role}'"}
                else:
                    await log_step(
                        task_id,
                        f"[{agent.name}] calling tool: {tool_name}({json.dumps(tool_args)[:120]})",
                        source=agent.name,
                        level="debug",
                    )
                    ws = workspace_dir or f"/tmp/lucy-workspace/task_{task_id}"
                    tool_start = time.monotonic()
                    tool_result = await execute_tool(tool_name, tool_args, ws)
                    tool_duration = int((time.monotonic() - tool_start) * 1000)

                    record = {
                        "tool_name": tool_name,
                        "agent_name": agent.name,
                        "input_args": tool_args,
                        "output": tool_result,
                        "duration_ms": tool_duration,
                        "status": "error" if "error" in tool_result else "success",
                    }
                    accumulated_tool_calls.append(record)

                    await log_step(
                        task_id,
                        f"[{agent.name}] {tool_name} → {('error: ' + tool_result['error']) if 'error' in tool_result else 'success'}",
                        source=agent.name,
                        level="agent",
                    )

                # Append tool call + result to message context
                tool_context = (
                    f"\n[Tool used: {tool_name}]\n"
                    f"Args: {json.dumps(tool_args, indent=2)}\n"
                    f"Result: {json.dumps(tool_result, indent=2)}\n"
                )
                messages.append({"role": "assistant", "content": _strip_tool_call(response_text)})
                messages.append({"role": "user", "content": f"Tool result:\n{tool_context}\nContinue your response."})

            # Persist step
            step.response = final_response
            step.duration_ms = total_duration_ms
            step.status = StepStatus.COMPLETED

            agent.state = AgentState.IDLE
            if agent.avg_response_time_ms is not None:
                agent.avg_response_time_ms = round(
                    agent.avg_response_time_ms * 0.8 + total_duration_ms * 0.2, 1
                )
            else:
                agent.avg_response_time_ms = float(total_duration_ms)
            await session.commit()

            tools_used = len(accumulated_tool_calls)
            await log_step(
                task_id,
                f"[{agent.name}] completed in {total_duration_ms}ms"
                + (f" using {tools_used} tool(s)" if tools_used else ""),
                source=agent.name,
                level="agent",
            )

            result = AgentResult(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_role=role,
                model_name=agent.model_name or "unknown",
                response=final_response,
                duration_ms=total_duration_ms,
                status="completed",
                step_label=step_label,
            )
            result.tool_calls = accumulated_tool_calls  # type: ignore[attr-defined]
            return result

        except Exception as e:
            step.status = StepStatus.FAILED
            step.response = f"ERROR: {str(e)}"
            agent.state = AgentState.FAILED
            agent.crash_count = (agent.crash_count or 0) + 1
            await session.commit()

            await log_step(
                task_id,
                f"[{agent.name}] FAILED: {str(e)}",
                source=agent.name,
                level="error",
            )
            result = AgentResult(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_role=role,
                model_name=agent.model_name or "unknown",
                response=f"ERROR: {str(e)}",
                duration_ms=0,
                status="failed",
                step_label=step_label,
            )
            result.tool_calls = []  # type: ignore[attr-defined]
            return result
