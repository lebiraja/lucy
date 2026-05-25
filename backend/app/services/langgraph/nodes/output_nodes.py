"""Structured output node — final node for all strategy graphs.

Converts flat LangGraph state into a rich structured dict that the
frontend can render: final answer, tool calls, agent steps, charts, rankings.
"""

from __future__ import annotations
import time
from app.services.langgraph.state import TaskState, AgentResult


def _agent_result_to_dict(r: AgentResult) -> dict:
    return {
        "agent_name": r.agent_name,
        "agent_role": r.agent_role,
        "model_name": r.model_name,
        "response": r.response,
        "duration_ms": r.duration_ms,
        "status": r.status,
        "step_label": r.step_label,
        "tool_calls": getattr(r, "tool_calls", []),
    }


async def build_structured_output_node(state: TaskState) -> dict:
    """Assemble the final StructuredOutput dict from all accumulated state."""
    all_responses: list[AgentResult] = state.get("agent_responses", [])
    opinions: list[AgentResult] = state.get("council_opinions", [])
    reviews: list[AgentResult] = state.get("council_reviews", [])
    all_steps = list(all_responses) + list(opinions) + list(reviews)

    # Gather all tool calls from all agent results
    all_tool_calls: list[dict] = list(state.get("tool_calls", []))
    for r in all_steps:
        tc = getattr(r, "tool_calls", [])
        if tc:
            all_tool_calls.extend(tc)

    # Gather charts from tool call results
    charts: list[str] = []
    files: list[str] = []
    for tc in all_tool_calls:
        output = tc.get("output", {})
        if isinstance(output, dict):
            if "base64" in output:
                charts.append(output["base64"])
            if "charts" in output:
                for c in output.get("charts", []):
                    if isinstance(c, dict) and "base64" in c:
                        charts.append(c["base64"])
            if "files_created" in output:
                files.extend(output.get("files_created", []))
            if "path" in output and output.get("success"):
                files.append(output["path"])

    structured = {
        "final_answer": state.get("final_output") or "",
        "tool_calls": all_tool_calls,
        "agent_steps": [_agent_result_to_dict(r) for r in all_steps],
        "rankings": state.get("council_rankings") or None,
        "strategy_used": state.get("strategy", ""),
        "files": list(set(files)) if files else None,
        "charts": charts if charts else None,
    }

    return {"structured_output": structured}
