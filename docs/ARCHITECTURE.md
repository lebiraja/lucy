# Lucy — Multi-Agent Orchestration Platform

## Architecture Overview

Lucy is a real-time orchestration platform for managing and coordinating multiple LLM agents. It runs multiple AI models simultaneously across a network of GPU servers and routes tasks through configurable strategies.

```
┌──────────────────────────────────────────────────────────────┐
│                         Browser                               │
│         React + Vite (Liquid Glass UI) — port 2000            │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP / WebSocket
                    ┌────────▼────────┐
                    │   nginx proxy    │  /api/* → backend:8000
                    └────────┬────────┘
                             │
               ┌─────────────▼─────────────┐
               │   FastAPI Backend (Python)  │  port 2800
               │   Uvicorn + asyncpg         │
               └──────┬───────────┬─────────┘
                      │           │
         ┌────────────▼──┐   ┌────▼──────────────┐
         │  PostgreSQL 16 │   │  vLLM Agent Fleet  │
         │  lucy_db       │   │  (remote GPUs)     │
         │  port 2543     │   │  OpenAI-compat API │
         └───────────────┘   └────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, shadcn/ui, Framer Motion |
| Backend | FastAPI, SQLAlchemy (async), Pydantic v2, asyncpg |
| Orchestration | **LangGraph** (StateGraph, conditional edges, MemorySaver checkpointing) |
| Database | PostgreSQL 16 |
| LLM Protocol | OpenAI-compatible `/v1/chat/completions` (vLLM / Ollama / OpenRouter) |
| Container | Docker Compose |
| Proxy | nginx (SPA fallback + API proxy) |

---

## Directory Structure

```
lucy/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, lifespan, /api/health, /api/logs
│   │   ├── config.py        # Settings from env vars (pydantic-settings)
│   │   ├── database.py      # Async SQLAlchemy engine + session factory
│   │   ├── models.py        # ORM models (Agent, Task, TaskStep, LogEntry)
│   │   ├── schemas.py       # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── agents.py    # Agent CRUD + health check endpoints
│   │   │   ├── tasks.py     # Task creation, listing, SSE streaming
│   │   │   └── ws.py        # WebSocket log streaming
│   │   └── services/
│   │       ├── orchestrator.py  # Thin adapter — delegates to LangGraph executor
│   │       ├── llm_client.py    # vLLM/Ollama/OpenRouter HTTP client
│   │       ├── logger.py        # Log broadcaster (pub/sub via asyncio.Queue)
│   │       └── langgraph/       # ★ LangGraph orchestration engine
│   │           ├── state.py         # TaskState, AgentResult, RankingResult
│   │           ├── executor.py      # GraphExecutor (builds + runs graphs)
│   │           ├── callbacks.py     # WebSocket log callback handlers
│   │           ├── graphs/
│   │           │   ├── sequential.py # Linear chain graph
│   │           │   ├── parallel.py   # Fan-out + synthesis graph
│   │           │   ├── dynamic.py    # Router + conditional edges
│   │           │   ├── council.py    # 3-stage deliberation subgraph
│   │           │   └── hierarchical.py # Multi-level agent delegation graph
│   │           │   └── planning.py   # Level 0.5 project planning subgraph
│   │           └── nodes/
│   │               ├── agent_nodes.py   # run_agent_step, ROLE_SYSTEM_PROMPTS
│   │               ├── routing_nodes.py # extract_json, ranking logic
│   │               ├── utility_nodes.py # log_step, persist_result, fail
│   │               ├── planning_nodes.py # Plan generation and agent allocation
│   │               └── delegation_nodes.py # CEO intake, Manager breakdown, etc.
│   └── test_migration.py   # 12 functional tests for LangGraph migration
│
├── liquid-glass-ui/         # The active frontend (Liquid Glass theme)
│   └── src/
│       ├── App.tsx           # Root router with ErrorBoundary per route
│       ├── components/
│       │   ├── AppLayout.tsx # Sidebar layout — uses real /api/health
│       │   ├── AppSidebar.tsx
│       │   ├── ErrorBoundary.tsx  # Prevents blank page on render errors
│       │   ├── GlassCard.tsx
│       │   └── StatusDot.tsx
│       ├── pages/
│       │   ├── Dashboard.tsx  # Health stats + agent fleet + recent tasks
│       │   ├── Agents.tsx     # CRUD for agents + hierarchy tree
│       │   ├── Tasks.tsx      # Task creation with strategy selector
│       │   ├── History.tsx    # Task history with step detail + council rankings
│       │   └── Monitor.tsx    # Live log terminal (polls /api/logs)
│       ├── lib/api.ts         # Typed API client (all endpoints)
│       └── types/lucy.ts      # Shared TypeScript interfaces
│
├── docker-compose.yml
└── docs/
    ├── ARCHITECTURE.md     ← you are here
    ├── LANGGRAPH.md        ← LangGraph engine deep dive
    ├── HIERARCHICAL.md     ← Hierarchical multi-agent implementation details
    ├── API.md
    ├── MULTI_AGENT_ARCHITECTURE.md
    └── FIXES.md
```

---

## Backend — Data Models

### Agent
Represents an LLM endpoint that can be assigned to tasks.

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-increment PK |
| `name` | str | Unique display name |
| `endpoint` | str | Base URL of vLLM/Ollama server |
| `model_name` | str? | Auto-detected from `/v1/models` |
| `role` | AgentRole | `ceo / cto / manager / employee` |
| `parent_id` | int? | FK → agents (hierarchy) |
| `operational_status` | enum | `active / inactive / paused / stopped / failed` |
| `infrastructure_status` | enum | `online / offline` |
| `state` | enum | `idle / assigned / planning / delegating / executing / waiting / reporting / completed / failed / stopped` |
| `is_orchestrator` | bool | Used by parallel/dynamic/council strategies |
| `temperature` | float | Per-agent generation temperature |
| `max_tokens` | int | Max tokens to generate per response |
| `top_p` | float | Nucleus sampling probability |
| `context_window_tokens` | int | Total context window; used for input truncation |
| `max_iterations` | int | Guard for loops |
| `timeout_seconds` | int | Per-agent request deadline |
| `crash_count` | int | Incremented on each failed call |
| `avg_response_time_ms` | float? | Exponential moving average |
| `is_warm` | bool | True if last health check succeeded |
| `last_heartbeat` | datetime? | Timestamp of last health check |

### Task
Represents a prompt dispatched to one or more agents.

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-increment PK |
| `prompt` | str | User-provided task description |
| `strategy` | TaskStrategy | `sequential / parallel / dynamic / council` |
| `status` | TaskStatus | `pending / running / completed / failed` |
| `final_output` | str? | Synthesized answer (populated on completion) |
| `task_metadata` | JSON? | Council stage data: rankings, opinions, reviews |
| `created_at` | datetime | |
| `completed_at` | datetime? | Set when task finishes |

### TaskStep
One agent invocation within a task.

| Field | Type | Description |
|---|---|---|
| `task_id` | int | FK → tasks |
| `agent_id` | int? | FK → agents (nullable if agent was deleted) |
| `step_order` | int | Index in execution sequence |
| `input_prompt` | str | Full prompt sent to this agent |
| `response` | str? | Agent's response text |
| `duration_ms` | int? | Wall-clock time for the LLM call |
| `status` | StepStatus | `pending / running / completed / failed` |
| `step_label` | str? | Stage label: `opinion / review / synthesis` |

### LogEntry
Real-time event log attached to tasks or the system.

| Field | Type | Description |
|---|---|---|
| `task_id` | int? | Optional FK → tasks |
| `level` | LogLevel | `info / warning / error / debug / agent` |
| `source` | str | `orchestrator` or agent name |
| `message` | str | Human-readable log text |
| `timestamp` | datetime | |

---

## Orchestration Strategies (LangGraph)

All strategies are implemented as **LangGraph StateGraphs** with typed state objects, conditional edges, and MemorySaver checkpointing. See [LANGGRAPH.md](LANGGRAPH.md) for the full engine deep dive.

### Sequential
Agents run one after another. Each agent receives the original prompt **plus all previous responses** as context. Good for iterative refinement tasks.

```
LangGraph: __start__ → sequential_chain → __end__

Agent A ─► response A ─► Agent B (context: A) ─► response B ─► ...final = last response
```

### Parallel
All agents run simultaneously receiving the identical prompt. Responses are synthesized by the orchestrator agent (if configured). Good for getting diverse perspectives quickly.

```
LangGraph: __start__ → fan_out → synthesize → __end__

                   ┌─► Agent A ─┐
Prompt ─► fan-out ─┤─► Agent B ─┼─► Orchestrator (synthesis) ─► final
                   └─► Agent C ─┘
```

### Dynamic
The orchestrator agent analyzes the prompt and **decides** which agents to invoke and in what order (returns a JSON routing decision). Falls back to parallel if no orchestrator is configured.

```
LangGraph: __start__ → router → [conditional] → run_sequential or run_parallel → __end__

Prompt ─► Orchestrator (routing JSON) ─► sequential or parallel sub-execution ─► final
```

### Council (3-Stage Deliberation)
Modeled after CEO-led boardroom decision-making. Implemented as a **6-node LangGraph subgraph** with conditional failure bail-out.

**Stage 1 — Individual Opinions (parallel, role-aware)**
Each agent generates their expert opinion using role-specific system prompts (CEO: strategy, CTO: technical, Manager: execution, Employee: detail).

**Stage 2 — Anonymous Blind Peer Review (parallel)**
All opinions are anonymized to labels (Response A, B, C…). Each agent reviews all responses and provides a structured **FINAL RANKING** section. Rankings are aggregated by average position (lower = better).

**Stage 3 — CEO Synthesis (single)**
The CEO/orchestrator agent receives all named opinions, all reviews, and the aggregate rankings. It produces the definitive final answer representing the council's collective wisdom.

```
LangGraph: __start__ → stage1_opinions → [check] → stage2_reviews → aggregate_rankings
                                           ↘ fail     → stage3_synthesis → persist_metadata → __end__

Stage 1: All agents ─► opinions (A, B, C, D)
Stage 2: All agents ─► anonymous review + ranking ─► aggregate leaderboard
Stage 3: CEO agent  ─► synthesis (full context + rankings) ─► final output
```

### Hierarchical (Multi-Level Delegation)
Modeled after a corporate management structure with a dynamic Level 0.5 planning graph.
See [HIERARCHICAL.md](HIERARCHICAL.md) for the full architecture.

**Levels:**
- **Level 0 (CEO):** Strategic oversight and priorities
- **Level 0.5 (Planning):** Questioning, project breakdown, dynamic agent allocation
- **Level 2 (CTO/Exec):** Technical breakdown and synthesis
- **Level 3 (Managers):** Checklist generation and task delegation
- **Level 4 (Employees/Devs/QA):** Parallel task execution

```
Client ─► CEO Intake ─► L0.5 Planning ─► CTO Breakdown ─► Managers
                                                                │
  CEO Approval ◄─ CTO Synthesis ◄─ Manager Review ◄─ Employee Execution
```

---

## Real-time Features

### Server-Sent Events (SSE)
`GET /api/tasks/{id}/events` streams log entries as they are produced during task execution. The client receives `data: {...}` events and a final `data: {"type": "done"}` event when the task completes or fails.

### WebSocket Log Streaming
- `ws://host/api/ws/logs` — global stream of all log entries
- `ws://host/api/ws/logs/{task_id}` — task-scoped stream

### HTTP Log Polling
`GET /api/logs?limit=200` returns the most recent log entries (used by the Monitor page every 2 seconds).

---

## Environment Variables

Create a `.env` file in the project root:

```env
# PostgreSQL
POSTGRES_USER=lucy
POSTGRES_PASSWORD=lucy_secret
POSTGRES_DB=lucy_db
DATABASE_URL=postgresql+asyncpg://lucy:lucy_secret@db:5432/lucy_db

# Port mapping (optional — defaults shown)
BACKEND_PORT=2800
FRONTEND_PORT=2000

# CORS (comma-separated, optional — sensible defaults included)
CORS_ORIGINS=http://localhost:2000,http://localhost:5173
```

---

## Running Locally

```bash
# Start all services
docker compose up -d

# Rebuild after frontend changes
docker compose build frontend && docker compose up -d frontend

# View live logs
docker compose logs -f backend

# Access the UI
open http://localhost:2000
```

---

## Agent Fleet Setup

1. Start at least one vLLM or Ollama instance on your network.
2. Navigate to **Agents → Add Agent** in the UI.
3. Enter the endpoint URL (e.g. `http://192.168.73.41:9002`).
4. Lucy auto-detects the model name via `/v1/models`.
5. Set the role and mark one agent as **Orchestrator** for parallel/dynamic/council strategies.
