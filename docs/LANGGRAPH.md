# Lucy — LangGraph Orchestration Engine

**Dependencies:** `langgraph>=0.4.1`, `langchain-core>=0.3.51`

---

## Overview

Lucy's orchestration engine is built on **LangGraph** — a framework for stateful, graph-based agent workflows. Five strategy graphs are pre-compiled at startup and dispatched by `GraphExecutor.run(state)` based on `state["strategy"]`.

Every graph now ends with `build_structured_output_node`, which assembles a rich `StructuredOutput` dict instead of a flat text string.

---

## Package Structure

```
services/langgraph/
├── state.py             # TaskState TypedDict, AgentResult, RankingResult
├── executor.py          # GraphExecutor singleton
├── graphs/
│   ├── sequential.py    # build_sequential_graph()
│   ├── parallel.py      # build_parallel_graph()
│   ├── dynamic.py       # build_dynamic_graph()
│   ├── council.py       # build_council_graph()
│   ├── hierarchical.py  # build_hierarchical_graph()
│   └── planning.py      # build_planning_graph() — L0.5 subgraph
└── nodes/
    ├── agent_nodes.py       # run_agent_step() + agentic tool loop
    ├── output_nodes.py      # build_structured_output_node()
    ├── routing_nodes.py     # extract_json(), ranking aggregation
    ├── utility_nodes.py     # log_step(), persist_result_node(), fail_node()
    ├── delegation_nodes.py  # CEO, CTO, Manager, Employee nodes
    └── planning_nodes.py    # Questioner, Planner, Allocation nodes
```

---

## State Model (`state.py`)

`TaskState` is the single TypedDict flowing through all graphs:

```python
class TaskState(TypedDict, total=False):
    # Core
    task_id: int
    prompt: str
    strategy: str
    agents: list[dict]

    # Session / conversation context
    session_id: int | None
    conversation_history: list[dict]          # [{"role": "user"|"assistant", "content": str}]
    tool_calls: Annotated[list[dict], operator.add]   # reducer: parallel-safe append
    workspace_dir: str | None

    # Execution
    agent_responses: Annotated[list[AgentResult], operator.add]
    current_step_order: int

    # Dynamic routing
    routing_decision: dict | None

    # Council
    council_opinions: list[AgentResult]
    council_reviews: list[AgentResult]
    council_rankings: list[RankingResult]
    label_to_agent: dict[str, int]

    # Output
    final_output: str | None
    structured_output: dict | None            # StructuredOutput assembled by output_nodes.py
    task_status: str                          # "running" | "completed" | "failed"
    error: str | None

    # Hierarchical
    project_id: int | None
    project_plan: dict | None
    agent_allocation: dict | None
    task_breakdown: list[dict]
    manager_checklists: dict
    hierarchy_results: Annotated[list[dict], operator.add]
    rework_count: int
    rework_needed: bool
```

---

## Agentic Tool Loop (`agent_nodes.py`)

`run_agent_step()` is the core execution primitive. It now runs an iterative tool-use loop:

```
1. Build messages:
   [system: role prompt + tool instructions]
   [conversation_history (past turns)]
   [user: current prompt]

2. Call vLLM chat_completion()

3. Parse response for <tool_call>{"tool": "...", "args": {...}}</tool_call>

4. If tool call found AND tool is permitted for agent's role:
   a. Execute tool via services/tools/execute_tool()
   b. Append to context:
      assistant: <stripped response>
      user: "Tool result:\n[Tool: X]\nArgs: ...\nResult: ..."
   c. Go to step 2

5. If no tool call (or max_tool_iterations reached):
   Return AgentResult with final_response + accumulated tool_calls[]
```

The `<tool_call>` tag is injected into the system prompt automatically via `get_tool_prompt(role)` in `services/tools/__init__.py`.

---

## Structured Output Node (`output_nodes.py`)

`build_structured_output_node` is the final node in all 5 graphs. It assembles:

```python
{
    "final_answer": state["final_output"],
    "tool_calls": all tool call records from all agent steps,
    "agent_steps": [{agent_name, agent_role, response, duration_ms, step_label, tool_calls}],
    "rankings": state["council_rankings"],      # council only
    "charts": [base64 PNGs from tool results],
    "files": [filenames written to workspace],
    "strategy_used": state["strategy"],
}
```

This is stored in `Task.task_metadata` and `Message.structured`.

---

## Strategy Graphs

### Sequential

```
START → sequential_chain → structured_output → END
```

Each agent receives `original prompt + previous agent response`. Breaks on first failure. `final_output` = last agent's response.

### Parallel

```
START → fan_out → synthesize → structured_output → END
```

All agents run concurrently with `asyncio.gather()`. If an orchestrator agent exists, it synthesizes all responses. Otherwise responses are concatenated.

### Dynamic

```
START → router → [sequential | parallel] → structured_output → END
```

Orchestrator agent analyzes the prompt and returns a JSON routing decision:
```json
{"strategy": "sequential", "agent_ids": [1, 3], "reasoning": "..."}
```
Falls back to parallel if no orchestrator or JSON parse fails.

### Council (3-Stage)

```
START → stage1_opinions → [fail?] → stage2_reviews → aggregate_rankings
       → stage3_synthesis → persist_metadata → structured_output → END
```

**Stage 1 — Opinions (parallel)**
All agents generate role-aware expert opinions simultaneously.

**Stage 2 — Anonymous Peer Review (parallel)**
Opinions are anonymized (Response A, B, C…). Each agent reviews all responses and provides a structured `FINAL RANKING:` section. Rankings are parsed and averaged.

**Stage 3 — CEO Synthesis**
CEO/orchestrator receives all named opinions + reviews + aggregate rankings, produces the definitive answer.

**Metadata** stored in `task_metadata`: label_to_agent map, aggregate rankings, parsed per-review rankings.

### Hierarchical (9 nodes + rework loop)

```
ceo_intake → planning_layer → cto_breakdown → manager_delegation
    → execution_fan_out → manager_review → [rework? → manager_delegation]
    → cto_synthesis → ceo_approval → persist_result → structured_output → END
```

**Rework loop** (fixed): `check_rework()` routes back to `manager_delegation` if `state["rework_needed"] == True` and `rework_count < 2`, otherwise proceeds to `cto_synthesis`.

**Planning subgraph** (L0.5):
```
questioning_node → planning_node → allocation_node
```

See [HIERARCHICAL.md](HIERARCHICAL.md) for the full delegation design.

---

## Graph Executor (`executor.py`)

`GraphExecutor` is a singleton that pre-compiles all 5 graphs at startup:

```python
class GraphExecutor:
    def __init__(self):
        memory = MemorySaver()
        self._graphs = {
            "sequential": build_sequential_graph().compile(checkpointer=memory),
            "parallel":   build_parallel_graph().compile(checkpointer=memory),
            "dynamic":    build_dynamic_graph().compile(checkpointer=memory),
            "council":    build_council_graph().compile(checkpointer=memory),
            "hierarchical": build_hierarchical_graph().compile(checkpointer=memory),
        }

    async def run(self, state: TaskState) -> dict:
        graph = self._graphs[state["strategy"]]
        config = {"configurable": {"thread_id": str(state["task_id"])}}
        result = await graph.ainvoke(state, config=config)
        return result
```

`MemorySaver` enables per-task checkpointing keyed by `task_id`, allowing graph state to be recovered on failure.

---

## Observability

Every node calls `log_step()` (in `utility_nodes.py`) which:
1. Writes a `LogEntry` to PostgreSQL
2. Broadcasts via `log_broadcaster` (asyncio pub/sub)
3. Reaches WebSocket subscribers and SSE streams simultaneously

Log levels used:
- `info` — graph lifecycle events
- `agent` — agent responses and tool calls
- `debug` — tool invocation details
- `error` — failures and exceptions
- `warning` — fallbacks and degraded paths

---

## Error Handling

- **Agent not found in DB** → returns `AgentResult(status="failed")`, node handles gracefully
- **LLM HTTP error** → raises exception, caught in `run_agent_step`, marks step FAILED, increments `crash_count`
- **Tool execution error** → tool returns `{"error": "..."}`, logged, appended to context, loop continues
- **All agents failed** (parallel/council) → returns `task_status: "failed"` immediately via fail node
- **Hierarchical missing roles** → nodes return empty dict, execution continues with degraded output
- **Graph exception** → caught in `orchestrator.execute_task()`, sets `task.status = FAILED`
- **Server restart mid-task** → lifespan hook marks all `RUNNING` tasks as `FAILED` on startup
