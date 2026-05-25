"""LangGraph state models for Lucy orchestration.

These typed state objects flow through LangGraph graphs. They integrate
with the existing DB models (Agent, Task, TaskStep, LogEntry) but are
in-memory only — persistence happens via the existing ORM layer.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict


@dataclass
class AgentResult:
    """Result from a single agent execution step."""
    agent_id: int
    agent_name: str
    agent_role: str
    model_name: str
    response: str
    duration_ms: int
    status: str  # "completed" | "failed"
    step_label: str | None = None  # "opinion" | "review" | "synthesis"


@dataclass
class RankingResult:
    """Aggregate ranking for one agent in the council strategy."""
    agent_id: int
    agent_name: str
    agent_role: str
    average_rank: float
    rankings_count: int
    label: str


class TaskState(TypedDict, total=False):
    """Primary state object flowing through all LangGraph graphs.

    Fields use LangGraph's reducer pattern where needed:
    - Annotated[list, operator.add] → parallel nodes can append safely.
    """
    # ── Core identifiers ──
    task_id: int
    prompt: str
    strategy: str  # "sequential" | "parallel" | "dynamic" | "council"

    # ── Agent pool (serialized as dicts for state transport) ──
    agents: list[dict]  # [{id, name, endpoint, model_name, role, ...}]

    # ── Execution results ──
    agent_responses: Annotated[list[AgentResult], operator.add]  # reducer: append
    current_step_order: int

    # ── Dynamic routing ──
    routing_decision: dict | None  # {strategy, agent_ids, reasoning}

    # ── Council-specific ──
    council_opinions: list[AgentResult]
    council_reviews: list[AgentResult]
    council_rankings: list[RankingResult]
    label_to_agent: dict[str, int]  # "Response A" → agent_id

    # ── Output ──
    final_output: str | None
    structured_output: dict | None   # rich structured output for frontend rendering
    task_status: str  # "running" | "completed" | "failed"
    error: str | None

    # ── Session / conversation context ──
    session_id: int | None
    conversation_history: list[dict]   # [{"role": "user"|"assistant", "content": str}]
    tool_calls: Annotated[list[dict], operator.add]  # accumulated tool call records
    workspace_dir: str | None          # session-scoped sandbox dir

    # ── Hierarchical delegation ──
    project_id: int | None
    project_plan: dict | None           # parsed plan from L0.5 planner
    agent_allocation: dict | None       # {role: count} from allocation node
    task_breakdown: list[dict]          # from CTO: [{task, assigned_to_role, status}]
    manager_checklists: dict            # {manager_id: [{item, status, assigned_to_agent_id}]}
    hierarchy_results: Annotated[list[dict], operator.add]  # generic parallel-safe reducer
    rework_count: int                   # loop guard for manager review cycle
