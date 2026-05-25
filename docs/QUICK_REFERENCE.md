# Lucy — Quick Reference

A cheat sheet for understanding how Lucy's multi-agent system is wired together.

---

## Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Backend | FastAPI (async Python) | HTTP API + SSE streaming |
| Orchestration | LangGraph StateGraphs | 5 strategy graphs with checkpointing |
| Concurrency | `asyncio.gather()` | Parallel agent execution |
| LLM Client | httpx (async, pooled) | OpenAI-compat requests to vLLM |
| Database | PostgreSQL 16 | Sessions, messages, tasks, agents, tool calls |
| ORM | SQLAlchemy Async | Model persistence |
| Real-time push | SSE + WebSocket | Live logs + message streaming |
| Pub/sub | `asyncio.Queue` | Log broadcasting |
| Tools | httpx, subprocess, pandas, matplotlib | Web search, code exec, charts, CSV |
| Frontend | React 18, Vite, TailwindCSS, Framer Motion | Chat UI + dashboards |
| Markdown | react-markdown, remark-gfm | Rich assistant responses |
| Reverse proxy | nginx | SPA + API proxy + WS upgrade |

---

## Communication Channels

### 1. HTTP REST (Request/Response)
```
POST   /api/sessions                       Create chat session
GET    /api/sessions                       List sessions
GET    /api/sessions/{id}                  Get session + messages
DELETE /api/sessions/{id}                  Delete session
POST   /api/sessions/{id}/messages         Send message → SSE stream
GET    /api/sessions/{id}/files            List workspace files
GET    /api/sessions/{id}/files/{name}     Download file

POST   /api/agents                         Register agent
GET    /api/agents                         List agents
PUT    /api/agents/{id}                    Update agent
DELETE /api/agents/{id}                    Remove agent
GET    /api/agents/health                  Health-check all
GET    /api/agents/hierarchy               Agent tree

POST   /api/tasks                          Create task (direct)
GET    /api/tasks/{id}                     Get task
GET    /api/tasks/{id}/events              SSE stream

POST   /api/projects                       Create project
POST   /api/projects/{id}/execute          Spawn hierarchical task
```

### 2. Server-Sent Events (Server Push)
- `POST /api/sessions/{id}/messages` → streams `log`, `heartbeat`, `done` events
- `GET /api/tasks/{id}/events` → streams task-scoped log events

### 3. WebSocket (Bidirectional Real-Time)
- `ws://host/api/ws/logs` — all log events globally
- `ws://host/api/ws/logs/{task_id}` — task-scoped events

### 4. Internal HTTP to vLLM
- Shared `httpx.AsyncClient` (created in lifespan, pooled)
- OpenAI-compat `POST /v1/chat/completions`
- 120s timeout, context-window-aware input truncation

### 5. Database (SQLAlchemy Async)
Per-request session via `get_db()` dependency. Background tasks and tool nodes use their own isolated `async_session()` for concurrency safety.

---

## Data Tables

| Table | Purpose |
|-------|---------|
| `agents` | LLM endpoints + role/hierarchy/metrics |
| `sessions` | Persistent chat threads |
| `messages` | User + assistant turns inside sessions |
| `tool_calls` | Audit log of every tool invocation |
| `tasks` | One orchestrated execution |
| `task_steps` | One agent invocation inside a task |
| `projects` | High-level multi-task initiatives |
| `log_entries` | Real-time event log |

---

## Orchestration Strategies at a Glance

| Strategy | Pattern | Use case |
|----------|---------|----------|
| **Sequential** | A → B → C (chain) | Iterative refinement |
| **Parallel** | A∥B∥C → synthesize | Diverse opinions, fast |
| **Dynamic** | Router → seq/parallel | Adaptive routing |
| **Council** | Opinions → blind review → CEO synth | High-stakes decisions |
| **Hierarchical** | CEO → Plan → CTO → Mgrs → Devs → bubble up | Multi-phase projects |

---

## Agent Tool Loop

```
User message
    ▼
Build messages: [system + tool docs, conversation_history, user prompt]
    ▼
LLM call ─────────────────────────────────────────────────┐
    ▼                                                       │
Parse for <tool_call>{"tool": "...", "args": {...}}</tool_call>
    ▼                                                       │
Tool call present?                                          │
    ├─ YES → execute tool in workspace                      │
    │        append "[Tool: X] Result: ..." to context ─────┘
    │        (up to MAX_TOOL_ITERATIONS=5)
    │
    └─ NO  → return final response + accumulated tool_calls
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `web_search` | SerpAPI Google search |
| `news_search` | NewsAPI recent articles |
| `run_code` | Sandboxed Python (pandas, numpy, matplotlib) |
| `run_shell` | Allowlist shell (ls, cat, grep, find...) |
| `read_file` | Read from session workspace |
| `write_file` | Write to session workspace |
| `generate_chart` | matplotlib chart → inline PNG |
| `parse_csv` | pandas CSV/Excel analysis |

Tool permissions are role-gated. See [TOOLS.md](TOOLS.md) for the full matrix.

---

## Structured Output Schema

Every task produces a `StructuredOutput` dict stored in `Task.task_metadata` and `Message.structured`:

```json
{
  "final_answer": "markdown answer",
  "tool_calls": [{ "tool_name", "agent_name", "input_args", "output", "duration_ms", "status" }],
  "agent_steps": [{ "agent_name", "agent_role", "response", "duration_ms", "step_label", "tool_calls" }],
  "rankings": [{ "agent_id", "agent_name", "average_rank", "rankings_count" }],
  "charts": ["base64 PNG", ...],
  "files": ["filename.csv", ...],
  "strategy_used": "council"
}
```

The frontend `StructuredOutputRenderer` consumes this directly.

---

## Concurrency Model

Single FastAPI process with one uvicorn event loop. Background tasks added via `asyncio.create_task`. Parallel agent calls via `asyncio.gather`. Per-tool subprocess isolation for code/shell execution.

---

## Error Handling

| Error | Source | Handling |
|-------|--------|----------|
| LLM HTTP timeout | httpx | Mark step FAILED, increment `crash_count` |
| LLM returns 5xx | vLLM | Logged, agent marked FAILED |
| Tool error | tool function | `{"error": "..."}` returned, appended to context, loop continues |
| All council opinions failed | council graph | Conditional edge → `fail` node → task FAILED |
| Server restart mid-task | lifespan | Marks all RUNNING tasks as FAILED |
| Graph exception | orchestrator | Sets `task.status = FAILED` with error in `final_output` |

---

## Key File Locations

```
backend/app/services/langgraph/nodes/agent_nodes.py     ← Agentic tool loop
backend/app/services/langgraph/nodes/output_nodes.py    ← Structured output builder
backend/app/services/tools/                              ← All tool implementations
backend/app/routers/sessions.py                          ← Chat session API + SSE
liquid-glass-ui/src/pages/Chat.tsx                       ← Main chat page
liquid-glass-ui/src/components/chat/                     ← Chat UI components
```
