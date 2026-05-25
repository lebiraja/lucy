# Lucy — LangGraph Orchestration Engine

**Date:** March 10, 2026  
**Engine Version:** 1.0  
**Dependencies:** `langgraph>=0.4.1`, `langchain-core>=0.3.51`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [State Model](#3-state-model)
4. [Node Reference](#4-node-reference)
5. [Strategy Graphs](#5-strategy-graphs)
6. [Graph Executor](#6-graph-executor)
7. [Execution Flow](#7-execution-flow)
8. [Checkpointing & Recovery](#8-checkpointing--recovery)
9. [Observability](#9-observability)
10. [Error Handling](#10-error-handling)
11. [Configuration](#11-configuration)
12. [Testing](#12-testing)

---

## 1. Overview

Lucy's orchestration engine is built on **LangGraph** — a framework for building stateful, graph-based agent workflows. The engine replaces the previous custom AsyncIO orchestrator while preserving all existing APIs, database schema, WebSocket logging, and agent abstractions.

### Key Design Principles

- **LangGraph replaces orchestration logic only** — no changes to API, DB, or WebSocket layers
- **`orchestrator.py` is a thin adapter** — delegates to LangGraph `GraphExecutor`
- **Each strategy = one `StateGraph`** — council uses a subgraph with conditional edges
- **Typed state objects** carry task context through graph execution
- **Session isolation preserved** — each node uses its own `async_session()` for safe concurrency

### Package Structure

```
services/langgraph/
├── __init__.py
├── state.py             ← TaskState TypedDict, AgentResult, RankingResult
├── executor.py          ← GraphExecutor singleton (builds + caches + invokes graphs)
├── callbacks.py         ← WebSocket log callback handlers
│
├── graphs/
│   ├── __init__.py
│   ├── sequential.py    ← build_sequential_graph()
│   ├── parallel.py      ← build_parallel_graph()
│   ├── dynamic.py       ← build_dynamic_graph()
│   ├── council.py       ← build_council_graph() — 6-node subgraph
│   ├── hierarchical.py  ← build_hierarchical_graph()
│   └── planning.py      ← build_planning_graph() (L0.5 subgraph)
│
└── nodes/
    ├── __init__.py
    ├── agent_nodes.py   ← run_agent_step(), ROLE_SYSTEM_PROMPTS
    ├── routing_nodes.py ← extract_json(), parse_ranking_from_text(), calculate_aggregate_rankings()
    ├── utility_nodes.py ← log_step(), persist_result_node(), fail_node()
    ├── planning_nodes.py   ← questioning, planning, allocation
    └── delegation_nodes.py ← ceo, cto, manager, execution
```

---

## 2. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                  FastAPI Application (Unchanged)                     │
│  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────────────────┐      │
│  │ /agents  │  │ /tasks   │  │  /ws   │  │ /tasks/{id}/events│     │
│  └──────────┘  └────┬─────┘  └───┬────┘  └──────────────────┘      │
│                     │            │                                   │
│  ┌──────────────────▼────────────▼──────────────────────────────┐   │
│  │      orchestrator.py (Thin Adapter)                          │   │
│  │  execute_task(session, task, agents) → GraphExecutor.run()   │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                       │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │              LangGraph Engine (services/langgraph/)           │   │
│  │                                                               │   │
│  │  ┌── GraphExecutor ──────────────────────────────────────┐   │   │
│  │  │  Pre-compiled graphs + MemorySaver checkpointing      │   │   │
│  │  │  .run(TaskState) → selects graph, ainvoke(), returns  │   │   │
│  │  └───────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌── Graphs ──────────────────────────────────────────────────┐  │
│  │  sequential │ parallel │ dynamic │ council │ hierarchical │  │
│  │  └────────────────────────────────────────────────────────────┘  │
│  │                                                               │   │
│  │  ┌── Nodes ───────────────────────────────────────────────┐  │   │
│  │  │  run_agent_step → chat_completion() → DB persist       │  │   │
│  │  │  log_step → LogEntry(DB) + LogBroadcaster              │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────┐  ┌────────────────────────────────────────┐     │
│  │ LogBroadcaster │  │ SQLAlchemy (Agent,Task,TaskStep,Log)    │     │
│  │ (Unchanged)    │  │ PostgreSQL (Unchanged schema)           │     │
│  └────────────────┘  └────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### How It Integrates

1. `POST /api/tasks` → `_run_task_background()` → `execute_task(session, task, agents)`
2. `orchestrator.py` serializes `Agent` ORM objects to dicts → builds `TaskState`
3. `GraphExecutor.run(state)` selects the compiled graph by `strategy` and calls `ainvoke()`
4. Graph nodes call `run_agent_step()` → `chat_completion()` → persist `TaskStep` to DB
5. Each node calls `log_step()` → `LogEntry` to DB + `LogBroadcaster.broadcast()`
6. Final result flows back to `orchestrator.py` → updates `Task` ORM record

---

## 3. State Model

### TaskState (TypedDict)

The primary state object flowing through all graphs. Uses LangGraph's **reducer pattern** for safe parallel node writes.

```python
class TaskState(TypedDict, total=False):
    # Core identifiers
    task_id: int
    prompt: str
    strategy: str                                      # "sequential"|"parallel"|"dynamic"|"council"|"hierarchical"

    # Agent pool (serialized as dicts)
    agents: list[dict]                                 # [{id, name, endpoint, model_name, role, ...}]

    # Execution results
    agent_responses: Annotated[list[AgentResult], operator.add]  # ← reducer: parallel-safe append
    current_step_order: int

    # Dynamic routing
    routing_decision: dict | None                      # {strategy, agent_ids, reasoning}

    # Council-specific
    council_opinions: list[AgentResult]
    council_reviews: list[AgentResult]
    council_rankings: list[RankingResult]
    label_to_agent: dict[str, int]                     # "Response A" → agent_id

    # Hierarchical
    project_id: int | None
    project_plan: dict | None
    agent_allocation: dict | None
    task_breakdown: list[dict]
    manager_checklists: dict
    hierarchy_results: Annotated[list[dict], operator.add]
    rework_count: int

    # Output
    final_output: str | None
    task_status: str                                   # "running"|"completed"|"failed"
    error: str | None
```

### AgentResult (dataclass)

```python
@dataclass
class AgentResult:
    agent_id: int
    agent_name: str
    agent_role: str        # "ceo"|"cto"|"manager"|"employee"
    model_name: str
    response: str
    duration_ms: int
    status: str            # "completed"|"failed"
    step_label: str | None # "opinion"|"review"|"synthesis"
```

### RankingResult (dataclass)

```python
@dataclass
class RankingResult:
    agent_id: int
    agent_name: str
    agent_role: str
    average_rank: float
    rankings_count: int
    label: str             # "Response A", "Response B", etc.
```

---

## 4. Node Reference

### `agent_nodes.py`

| Function | Purpose |
|---|---|
| `run_agent_step(task_id, agent_dict, prompt, step_order, step_label)` | Core agent execution — creates `TaskStep`, calls `chat_completion()`, updates agent metrics (EMA response time, crash count), returns `AgentResult` |
| `ROLE_SYSTEM_PROMPTS` | Dict mapping role → system prompt for council opinions |

### `routing_nodes.py`

| Function | Purpose |
|---|---|
| `extract_json(text)` | Strip markdown code fences and return raw JSON |
| `parse_ranking_from_text(text, valid_labels)` | Extract ordered ranking labels from LLM review output |
| `calculate_aggregate_rankings(reviews, label_to_id, label_to_info)` | Compute average rank position per agent from peer reviews |

### `utility_nodes.py`

| Function | Purpose |
|---|---|
| `log_step(task_id, message, level, source)` | Persist `LogEntry` to DB + broadcast via `LogBroadcaster` |
| `persist_result_node(state)` | Write `final_output` and `task_status` back to `Task` record |
| `fail_node(state)` | Terminal failure — returns failed status + error message |

---

## 5. Strategy Graphs

### Sequential Graph

Simple linear chain — each agent builds on the previous response.

```
__start__ ──► sequential_chain ──► __end__
```

- **Nodes:** 1 (`sequential_chain_node`)
- **Edges:** Linear
- **Failure mode:** Chain breaks on first agent failure
- **Final output:** Last agent's response

### Parallel Graph

Fan-out to all agents concurrently, then synthesize with orchestrator agent.

```
__start__ ──► fan_out ──► synthesize ──► __end__
```

- **Nodes:** 2 (`parallel_fan_out_node`, `synthesize_parallel_node`)
- **Edges:** Linear
- **Concurrency:** `asyncio.gather()` in fan_out node
- **Fallback:** Concatenates responses if no orchestrator agent available
- **Failure mode:** Skips failed agents; fails only if ALL agents fail

### Dynamic Graph

Orchestrator agent decides routing strategy via JSON, then delegates.

```
__start__ ──► router ──► [conditional] ──┬── run_sequential ──► __end__
                                         └── run_parallel   ──► __end__
```

- **Nodes:** 3 (`dynamic_router_node`, `apply_sequential`, `apply_parallel`)
- **Edges:** Conditional after `router` node
- **Routing function:** `route_after_decision()` reads `routing_decision.strategy`
- **Fallback:** Defaults to `parallel` if orchestrator fails or returns invalid JSON
- **Failure mode:** Falls back to parallel on any routing error

### Council Graph (Subgraph)

6-node subgraph implementing 3-stage CEO-led deliberation.

```
__start__ ──► stage1_opinions ──► [check] ──► stage2_reviews ──► aggregate_rankings ──►
                                      │                                                  │
                                      └──► fail ──► __end__      stage3_synthesis ──► persist_metadata ──► __end__
```

- **Nodes:** 6 (`opinion_fan_out_node`, `review_fan_out_node`, `aggregate_rankings_node`, `synthesis_node`, `persist_council_metadata_node`, `council_fail_node`)
- **Conditional edge:** After `stage1_opinions` — checks if at least one opinion succeeded
- **Anonymous labeling:** Opinions ↔ labels (A, B, C...) — agents can't see who wrote what
- **Ranking aggregation:** Average rank position across all reviews (lower = better)
- **CEO synthesis:** Receives all named opinions + anonymous reviews + rankings
- **Metadata persistence:** Rankings + label maps stored in `task.task_metadata` (JSON)
- **Failure mode:** Bails out to `fail` node if all opinions fail; CEO synthesis falls back to concatenation

### Hierarchical Graph

Full corporate delegation structure with a dynamic Level 0.5 planning phase.

```
__start__ ──► ceo_intake ──► planning_layer ──► cto_breakdown ──► manager_delegation
                                                                           │
  __end__ ◄── ceo_approval ◄── cto_synthesis ◄── manager_review ◄── execution_fan_out
```

- **Nodes:** 8 core nodes, plus `planning_layer` acts as a 3-node subgraph
- **Planning layer:** Subgraph that handles requirement questioning, project planning, and agent unit allocation
- **Manager loop:** `manager_review` can loop back to `execution_fan_out` if rework is required (guard: `rework_count`)
- **Use case:** Massive multi-agent projects lasting multiple steps or phases, tracked via the `Project` database model.

---

## 6. Graph Executor

### GraphExecutor Class

Singleton that pre-compiles and caches all strategy graphs with checkpointing.

```python
class GraphExecutor:
    def __init__(self):
        self._checkpointer = MemorySaver()
        self._graphs = {
            "sequential": build_sequential_graph().compile(checkpointer=...),
            "parallel":   build_parallel_graph().compile(checkpointer=...),
            "dynamic":    build_dynamic_graph().compile(checkpointer=...),
            "council":    build_council_graph().compile(checkpointer=...),
        }

    async def run(self, state: TaskState) -> TaskState:
        strategy = state["strategy"]
        graph = self._graphs[strategy]
        config = {"configurable": {"thread_id": f"task-{state['task_id']}"}}
        return await graph.ainvoke(state, config=config)
```

### Graph Caching

Graphs are compiled **once** at import time and reused across all task executions. This avoids the overhead of rebuilding the graph structure on every request.

### Thread ID Convention

Each task gets a unique `thread_id = f"task-{task_id}"` for checkpointing. This enables:
- Inspecting intermediate state during execution
- Potential task resumption after crashes (with persistent checkpointer)

---

## 7. Execution Flow

### Complete Request Lifecycle

```
POST /api/tasks
  │
  ▼
routers/tasks.py :: create_task()
  ├─ Create Task(PENDING) in DB
  ├─ Spawn asyncio background task
  └─ Return 201 + task_id
  │
  ▼
routers/tasks.py :: _run_task_background()
  ├─ Load agents from DB
  └─ Call execute_task(session, task, agents)
  │
  ▼
orchestrator.py :: execute_task()
  ├─ Set task.status = RUNNING
  ├─ Serialize Agent ORM → dicts
  ├─ Build TaskState
  └─ await graph_executor.run(state)
  │
  ▼
executor.py :: GraphExecutor.run()
  ├─ Select compiled graph by strategy
  └─ await graph.ainvoke(state, config)
  │
  ▼
[LangGraph nodes execute]
  ├─ run_agent_step() → chat_completion() → TaskStep(DB)
  ├─ log_step() → LogEntry(DB) + WebSocket broadcast
  ├─ [strategy-specific logic]
  └─ Returns final TaskState
  │
  ▼
orchestrator.py :: execute_task()
  ├─ Write result.final_output → task.final_output
  ├─ Write result.task_status → task.status
  └─ session.flush()
```

---

## 8. Checkpointing & Recovery

### MemorySaver (Current)

The engine uses `MemorySaver` for in-memory checkpointing. This provides:
- State snapshots at each node transition
- Potential for mid-execution inspection
- Thread-safe operation across concurrent tasks

### Upgrading to Persistent Checkpointing

To enable task resumption after server crashes, replace `MemorySaver` with a persistent backend:

```python
# In executor.py, replace:
self._checkpointer = MemorySaver()

# With (PostgreSQL example):
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
self._checkpointer = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
```

### Crash Recovery

The current `main.py` lifespan marks all in-flight tasks as `FAILED` on startup:

```python
await conn.execute(
    sa_update(Task)
    .where(Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]))
    .values(status=TaskStatus.FAILED, final_output="Server restarted...")
)
```

With persistent checkpointing, this could be changed to resume tasks from their last checkpoint instead.

---

## 9. Observability

### Log Flow

Every graph node calls `log_step()` which:

1. **Persists** a `LogEntry` to the database (isolated session)
2. **Broadcasts** via `LogBroadcaster` to all WebSocket subscribers

### WebSocket Events

Logs are delivered in real-time to:
- `ws://host/api/ws/logs` — global stream
- `ws://host/api/ws/logs/{task_id}` — task-specific stream

### LangGraph Callbacks

Optional node lifecycle events via `callbacks.py`:
- `on_node_start(node_name, task_id)` — fired when a node begins
- `on_node_end(node_name, task_id)` — fired when a node completes

### Agent Metrics

Updated inside `run_agent_step()` on every LLM call:
- `avg_response_time_ms` — exponential moving average (α=0.2)
- `crash_count` — incremented on each failure
- `state` — transitions: `IDLE → EXECUTING → IDLE` (or `→ FAILED`)
- `last_heartbeat` — updated before each call

---

## 10. Error Handling

### Per-Strategy Error Behavior

| Strategy | On Agent Failure |
|---|---|
| **Sequential** | Chain breaks immediately — task fails with last successful output |
| **Parallel** | Failed agents skipped — task succeeds if any agent succeeds |
| **Dynamic** | Router failure → falls back to parallel execution |
| **Council** | Stage 1: failed opinions excluded. Stage 2+3: CEO synthesis falls back to concatenation |

### Node-Level Error Handling

- `run_agent_step()` catches all exceptions, persists `TaskStep(FAILED)`, increments `crash_count`, and returns `AgentResult(status="failed")`
- Each graph node checks for failure conditions and routes accordingly
- Council graph has a conditional edge that bails to `fail_node` if all Stage 1 opinions fail

### Dynamic Router Fallbacks

The `route_after_decision()` function handles these edge cases:
- `routing_decision` is `None` → defaults to `parallel`
- `routing_decision` is not a `dict` → defaults to `parallel`
- `strategy` key missing → defaults to `parallel`
- JSON parse failure → defaults to `parallel` with all non-orchestrator agents

---

## 11. Configuration

### Dependencies

```
# requirements.txt
langgraph>=0.4.1
langchain-core>=0.3.51
```

### Environment Variables

No new environment variables are needed. The LangGraph engine uses the same configuration as the existing system:

| Variable | Used By | Default |
|---|---|---|
| `DATABASE_URL` | All DB operations in nodes | `postgresql+asyncpg://...` |
| `LLM_REQUEST_TIMEOUT` | `chat_completion()` via `llm_client.py` | `120.0` |

### Docker

The `docker-compose.yml` volume mount `./backend:/app` means code changes are reflected immediately. Dependencies are installed during `docker compose build backend`.

---

## 12. Testing

### Migration Test Suite

Run the 12-test functional suite inside Docker:

```bash
docker compose exec backend python test_migration.py
```

**Tests cover:**

| # | Test | What it validates |
|---|---|---|
| 1 | GraphExecutor init | All 4 strategy graphs pre-compiled |
| 2 | TaskState creation | TypedDict matches expected schema |
| 3 | AgentResult | Dataclass fields and defaults |
| 4a-d | Routing helpers | `extract_json`, `parse_ranking` with edge cases |
| 5 | Aggregate rankings | Average rank computation with ties |
| 6 | execute_task signature | `['session', 'task', 'agents']` preserved |
| 7 | ROLE_SYSTEM_PROMPTS | All 4 roles present with correct content |
| 8 | Council graph structure | All 8 nodes present including conditional edges |
| 9 | Dynamic routing | Conditional edge handles `None`, missing keys, valid strategies |
| 10 | DB session compatibility | ORM queries work from LangGraph context |
| 11 | log_step persistence | `LogEntry` created in DB and retrievable |
| 12 | tasks.py compatibility | `_run_task_background` still callable |

### Manual End-to-End Testing

1. Create agents via UI or `POST /api/agents`
2. Run each strategy via `POST /api/tasks`:
   ```json
   {"prompt": "Your question", "strategy": "council", "agent_ids": [1, 2, 3]}
   ```
3. Monitor logs via WebSocket: `ws://localhost:2800/api/ws/logs/{task_id}`
4. Verify task results: `GET /api/tasks/{task_id}`
5. Check council metadata in `task.task_metadata` field
