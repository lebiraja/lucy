# Lucy — Architecture

## System Topology

```
Browser (port 2000)
        │
        ▼
  ┌─────────────┐
  │    nginx     │  /api/* → backend:8000
  │  (frontend)  │  /     → React SPA
  └──────┬──────┘
         │
         ▼
  ┌──────────────────────────────┐
  │   FastAPI Backend (port 2800) │
  │   Uvicorn + asyncpg           │
  │                               │
  │  Routers:                     │
  │   /api/sessions  ← NEW        │
  │   /api/agents                 │
  │   /api/tasks                  │
  │   /api/projects               │
  │   /api/ws (WebSocket)         │
  └────┬──────────────┬───────────┘
       │              │
       ▼              ▼
 PostgreSQL 16    LangGraph Engine
  (lucy_db)       (5 strategy graphs)
                       │
                       ▼
               vLLM Agent Fleet
               (remote GPUs, OpenAI-compat)
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, shadcn/ui, Framer Motion |
| Backend | FastAPI, SQLAlchemy (async), Pydantic v2, asyncpg |
| Orchestration | LangGraph StateGraphs, MemorySaver checkpointing |
| Tools | httpx (SerpAPI, NewsAPI), subprocess sandbox (Python/shell), matplotlib, pandas |
| Database | PostgreSQL 16 |
| LLM Protocol | OpenAI-compatible `/v1/chat/completions` (vLLM / Ollama / OpenRouter) |
| Container | Docker Compose |
| Proxy | nginx (SPA fallback + API proxy + WebSocket upgrade) |

---

## Directory Structure

```
lucy/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, /health, /logs
│   │   ├── config.py            # Settings (pydantic-settings, reads .env)
│   │   ├── database.py          # Async SQLAlchemy engine + session factory
│   │   ├── models.py            # ORM: Agent, Session, Message, Task, TaskStep, LogEntry, ToolCallRecord
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── sessions.py      # Session CRUD + SSE message streaming (NEW)
│   │   │   ├── agents.py        # Agent CRUD + health checks
│   │   │   ├── tasks.py         # Task creation, listing, SSE events
│   │   │   ├── projects.py      # Project management
│   │   │   └── ws.py            # WebSocket log streaming
│   │   └── services/
│   │       ├── orchestrator.py  # Thin adapter → LangGraph executor
│   │       ├── llm_client.py    # vLLM HTTP client (context-aware truncation)
│   │       ├── logger.py        # Pub/sub log broadcaster (asyncio.Queue)
│   │       ├── tools/           # Agent tool system (NEW)
│   │       │   ├── __init__.py  # Registry, permissions, tool prompt builder
│   │       │   ├── web_search.py
│   │       │   ├── news_search.py
│   │       │   ├── code_interpreter.py
│   │       │   ├── shell_executor.py
│   │       │   ├── file_manager.py
│   │       │   ├── chart_generator.py
│   │       │   └── parse_csv.py
│   │       └── langgraph/
│   │           ├── state.py         # TaskState TypedDict + AgentResult dataclass
│   │           ├── executor.py      # GraphExecutor singleton
│   │           ├── graphs/
│   │           │   ├── sequential.py
│   │           │   ├── parallel.py
│   │           │   ├── dynamic.py
│   │           │   ├── council.py
│   │           │   ├── hierarchical.py
│   │           │   └── planning.py
│   │           └── nodes/
│   │               ├── agent_nodes.py     # run_agent_step + agentic tool loop (UPDATED)
│   │               ├── output_nodes.py    # build_structured_output_node (NEW)
│   │               ├── routing_nodes.py
│   │               ├── utility_nodes.py
│   │               ├── delegation_nodes.py
│   │               └── planning_nodes.py
│   └── requirements.txt
│
├── liquid-glass-ui/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── AppLayout.tsx
│       │   ├── AppSidebar.tsx
│       │   └── chat/              # Chat UI components (NEW)
│       │       ├── ChatMessage.tsx
│       │       ├── ChatInput.tsx
│       │       ├── SessionSidebar.tsx
│       │       ├── StructuredOutputRenderer.tsx
│       │       ├── ToolCallCard.tsx
│       │       └── AgentStepAccordion.tsx
│       ├── pages/
│       │   ├── Chat.tsx           # Primary chat page (NEW)
│       │   ├── Dashboard.tsx
│       │   ├── Agents.tsx
│       │   ├── Tasks.tsx
│       │   ├── History.tsx
│       │   └── Monitor.tsx
│       ├── lib/api.ts
│       └── types/lucy.ts
│
├── docker-compose.yml
├── .env
└── docs/
```

---

## Data Models

### Session
Persistent conversation thread. Stores strategy preference and pinned agents.

| Field | Type | Description |
|---|---|---|
| `id` | int | PK |
| `title` | str? | Auto-generated from first message |
| `strategy` | TaskStrategy | Default orchestration strategy |
| `agent_ids` | JSON? | Pinned agent IDs (null = all active) |
| `created_at` | datetime | |
| `updated_at` | datetime | Updated on each new message |

### Message
One turn in a conversation (user or assistant).

| Field | Type | Description |
|---|---|---|
| `id` | int | PK |
| `session_id` | int | FK → sessions |
| `role` | str | `"user"` or `"assistant"` |
| `content` | str | Plain text content |
| `structured` | JSON? | `StructuredOutput` dict for assistant messages |
| `task_id` | int? | FK → tasks (links to execution record) |

### ToolCallRecord
Audit log of every tool invocation by an agent.

| Field | Type | Description |
|---|---|---|
| `message_id` | int | FK → messages |
| `tool_name` | str | `"web_search"`, `"run_code"`, etc. |
| `agent_name` | str | Which agent called the tool |
| `input_args` | JSON? | Arguments passed to the tool |
| `output` | JSON? | Tool result or error |
| `duration_ms` | int? | Tool execution time |
| `status` | str | `"success"` or `"error"` |

### Agent
LLM endpoint registered in the system.

| Field | Type | Description |
|---|---|---|
| `name` | str | Unique display name |
| `endpoint` | str | vLLM base URL |
| `model_name` | str? | Auto-detected from `/v1/models` |
| `role` | AgentRole | `ceo / cto / manager / developer / employee / ...` |
| `parent_id` | int? | FK → agents (hierarchy) |
| `is_orchestrator` | bool | Used by parallel/dynamic/council strategies |
| `operational_status` | enum | `active / inactive / paused / stopped / failed` |
| `infrastructure_status` | enum | `online / offline` |
| `state` | enum | `idle / executing / planning / ...` |
| `capabilities` | JSON? | `["code_review", "testing"]` |
| `hierarchy_level` | int | 0=CEO, 1=Planning, 2=CTO, 3=Manager, 4=Employee |

### Task
One orchestrated execution (spawned per chat message or direct API call).

| Field | Type | Description |
|---|---|---|
| `project_id` | int? | FK → projects |
| `session_id` | int? | FK → sessions |
| `prompt` | str | The user's question |
| `strategy` | TaskStrategy | Which graph was used |
| `status` | TaskStatus | `pending / running / completed / failed` |
| `final_output` | str? | Plain text final answer |
| `task_metadata` | JSON? | Full `StructuredOutput` (tool calls, agent steps, charts, rankings) |

---

## Conversation Flow

```
User sends message in Chat UI
        │
        ▼
POST /api/sessions/{id}/messages
        │
        ├── Persist user Message to DB
        ├── Build conversation_history from past messages
        ├── Create Task (session_id, strategy, prompt)
        │
        ▼
execute_task(session, task, agents, conversation_history, workspace_dir)
        │
        ▼
LangGraph GraphExecutor.run(initial_state)
        │
   Each agent node:
        ├── Build messages: system prompt + tool instructions + history + user prompt
        ├── Call vLLM chat_completion()
        ├── If <tool_call> found:
        │     ├── Execute tool (web_search, run_code, etc.)
        │     ├── Append result to message context
        │     └── Re-call LLM (up to max_tool_iterations=5)
        └── Return AgentResult with response + tool_calls[]
        │
        ▼
build_structured_output_node()
        │  Produces:
        │  { final_answer, tool_calls, agent_steps, rankings, charts, files, strategy_used }
        │
        ▼
Persist to Task.task_metadata + Message.structured
        │
        ▼
SSE "done" event → Frontend renders StructuredOutputRenderer
```

---

## Tool Agentic Loop

Each agent step now runs an iterative loop instead of a single LLM call:

```
1. Build prompt (system + tool instructions + history + user message)
2. Call LLM
3. Parse response for <tool_call>{"tool": "...", "args": {...}}</tool_call>
4. If found:
     a. Check tool is permitted for agent's role
     b. Execute tool in session workspace (/tmp/lucy-workspace/session_{id}/)
     c. Append "[Tool: X] Result: ..." to message context
     d. Go to step 2
5. If no tool call (or max iterations reached): return final response
```

Tool permission matrix:

| Role | Tools |
|------|-------|
| CEO | web_search, news_search |
| CTO | web_search, run_code, run_shell, read_file, write_file, generate_chart |
| CFO | web_search, news_search, parse_csv, generate_chart |
| Manager | web_search, news_search, read_file, write_file |
| Developer | web_search, run_code, run_shell, read_file, write_file, generate_chart, parse_csv |
| Employee | web_search, run_code, read_file, write_file, generate_chart, parse_csv |
| Tester | run_code, run_shell, read_file, write_file |
| Planner / Questioner | web_search, news_search |

---

## Structured Output

Every task now produces a `StructuredOutput` dict stored in `Task.task_metadata` and `Message.structured`:

```json
{
  "final_answer": "The markdown answer...",
  "tool_calls": [
    {
      "tool_name": "web_search",
      "agent_name": "Aria",
      "input_args": { "query": "latest AI news" },
      "output": { "results": [...] },
      "duration_ms": 312,
      "status": "success"
    }
  ],
  "agent_steps": [
    {
      "agent_name": "Aria",
      "agent_role": "ceo",
      "response": "...",
      "duration_ms": 1840,
      "status": "completed",
      "step_label": "synthesis",
      "tool_calls": [...]
    }
  ],
  "rankings": null,
  "charts": ["<base64 png>"],
  "files": ["analysis.csv"],
  "strategy_used": "council"
}
```

The frontend `StructuredOutputRenderer` component renders this as:
- Markdown (with syntax-highlighted code blocks and tables)
- Inline chart images
- Collapsible tool call cards
- Council rankings table
- File download links
- Agent step accordion

---

## Real-time Streaming

### Session Message SSE
`POST /api/sessions/{id}/messages` returns a streaming response:

```
data: {"type": "log", "data": "{\"level\":\"agent\",\"source\":\"Aria\",\"message\":\"[Aria] calling tool: web_search...\"}"}
data: {"type": "log", "data": "..."}
data: {"type": "heartbeat"}
data: {"type": "done", "message": { ...full MessageResponse... }}
```

The frontend reads the stream, shows live log lines while waiting, then renders the final structured message.

### WebSocket Logs
- `ws://host/api/ws/logs` — all log events globally
- `ws://host/api/ws/logs/{task_id}` — task-scoped events

---

## File Workspace

Each session gets a sandboxed directory: `/tmp/lucy-workspace/session_{id}/`

- `run_code` executes scripts here and detects new files
- `write_file` / `read_file` are restricted to this directory (path traversal blocked)
- Charts saved as `.png` files are base64-encoded and included in `structured.charts`
- Files downloadable via `GET /api/sessions/{id}/files/{filename}`
- Mounted as a Docker volume (`lucy_workspace`) so files persist across backend restarts
