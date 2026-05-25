# Lucy — API Reference

Base URL: `http://localhost:2800` (direct) or `/api` (via nginx at port 2000)

---

## Health & Logs

### `GET /api/health`
```json
{
  "status": "ok",
  "total_agents": 3,
  "online_agents": 2,
  "active_tasks": 1,
  "completed_tasks": 12,
  "failed_tasks": 1,
  "success_rate": 92,
  "uptime_seconds": 3600
}
```

### `GET /api/logs?limit=100&offset=0`
Returns recent system-wide log entries (array of `LogEntry`).

---

## Sessions

Sessions are persistent conversation threads. Each session stores a strategy, optional pinned agents, and a history of messages.

### `POST /api/sessions`
Create a new session.

**Request**
```json
{
  "title": "My Research Session",
  "strategy": "dynamic",
  "agent_ids": [1, 2, 3]
}
```
`title` and `agent_ids` are optional. `strategy` defaults to `"dynamic"`.

**Response** — `SessionResponse`

---

### `GET /api/sessions`
List all sessions ordered by most recently updated.

**Response** — `SessionResponse[]`

---

### `GET /api/sessions/{id}`
Get a session with all its messages and tool call records.

---

### `DELETE /api/sessions/{id}`
Delete a session and all associated messages.

---

### `POST /api/sessions/{id}/messages`
Send a user message and stream the assistant response via **Server-Sent Events**.

**Request**
```json
{ "content": "Search the web for the latest AI research and summarize it" }
```

**SSE Stream**
```
data: {"type": "log", "data": "{\"level\":\"agent\",\"source\":\"Aria\",\"message\":\"calling web_search...\"}"}
data: {"type": "heartbeat"}
data: {"type": "done", "message": { ...MessageResponse... }}
```

- `log` events carry real-time orchestration progress
- `heartbeat` events keep the connection alive
- `done` carries the full final `MessageResponse` including `structured` output

**Reading the stream in JS**
```javascript
const response = await fetch(`/api/sessions/${id}/messages`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ content }),
});
const reader = response.body.getReader();
const decoder = new TextDecoder();
// read chunks, split on \n, parse "data: ..." lines
```

---

### `GET /api/sessions/{id}/messages`
List all messages in a session.

**Response** — `MessageResponse[]`

---

### `GET /api/sessions/{id}/files`
List files created by agents in the session workspace.

**Response** — `string[]` (filenames)

---

### `GET /api/sessions/{id}/files/{filename}`
Download a file from the session workspace.

---

## Agents

### `POST /api/agents`
Register a new agent.

**Request**
```json
{
  "name": "Aria",
  "endpoint": "http://192.168.73.41:9002",
  "model_name": "llama3.1:70b",
  "role": "ceo",
  "is_orchestrator": true,
  "temperature": 0.7,
  "max_tokens": 4096,
  "context_window_tokens": 128000
}
```
`model_name` is optional — auto-detected from the endpoint.

**Response** — `AgentResponse` | **Status** `201`

---

### `GET /api/agents`
List all agents.

### `GET /api/agents/{id}`
Get a specific agent.

### `PUT /api/agents/{id}`
Update agent configuration (any subset of fields).

### `DELETE /api/agents/{id}`
Remove an agent. **Status** `204`

### `GET /api/agents/health`
Health-check all agents in parallel. Updates `infrastructure_status` and `is_warm`.

**Response**
```json
[{ "id": 1, "name": "Aria", "is_online": true, "latency_ms": 42.3, "error": null }]
```

### `GET /api/agents/{id}/health`
Health-check a specific agent.

### `GET /api/agents/hierarchy`
Returns the full agent tree (recursive parent/child structure).

### `POST /api/agents/probe`
Discover models at a vLLM endpoint before registration.

**Request** — `{ "endpoint": "http://192.168.73.41:9002" }`

**Response**
```json
{
  "success": true,
  "model_name": "llama3.1:70b",
  "models": ["llama3.1:70b"],
  "max_model_len": 128000,
  "recommended_max_tokens": 4096
}
```

### `POST /api/agents/{id}/pause` / `resume` / `stop`
Update agent lifecycle state.

---

## Tasks

Tasks are low-level execution units. For conversational use, prefer the Sessions API.

### `POST /api/tasks`
Create and immediately execute a task.

**Request**
```json
{
  "prompt": "Design a microservices architecture",
  "strategy": "council",
  "agent_ids": [1, 2, 3]
}
```
`agent_ids` is optional (null = all active agents).

**Response** — `TaskResponse` (initial `status: "pending"`) | **Status** `201`

### `GET /api/tasks?limit=50&offset=0`
List all tasks with steps (agents eagerly loaded).

### `GET /api/tasks/{id}`
Get a task with all steps and agent info.

### `GET /api/tasks/{id}/logs`
All log entries for a task.

### `GET /api/tasks/{id}/events`
**SSE stream** for real-time task progress.
```
data: {"level": "agent", "source": "Aria", "message": "...", "task_id": 5, "timestamp": "..."}
data: {"type": "done", "status": "completed", "task_id": 5}
```

---

## Projects

### `POST /api/projects`
Create a project (for hierarchical execution).

**Request** — `{ "name": "...", "description": "..." }`

### `GET /api/projects`
List all projects with linked tasks.

### `GET /api/projects/{id}`
Get a project.

### `POST /api/projects/{id}/execute`
Spawn a hierarchical task for this project.

---

## WebSocket

### `WS /api/ws/logs`
Global log stream — all log entries from all tasks.

### `WS /api/ws/logs/{task_id}`
Task-scoped log stream.

**Message format** (JSON string)
```json
{ "level": "agent", "source": "Aria", "message": "...", "task_id": 5, "timestamp": "..." }
```

---

## Schema Reference

### `SessionResponse`
```typescript
{
  id: number;
  title: string | null;
  strategy: "sequential" | "parallel" | "dynamic" | "council" | "hierarchical";
  agent_ids: number[] | null;
  created_at: string;
  updated_at: string;
  messages: MessageResponse[];
}
```

### `MessageResponse`
```typescript
{
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  structured: StructuredOutput | null;
  task_id: number | null;
  created_at: string;
  tool_calls: ToolCallRecordResponse[];
}
```

### `StructuredOutput` (inside `message.structured` and `task.task_metadata`)
```typescript
{
  final_answer: string;
  tool_calls: ToolCallSummary[];
  agent_steps: AgentStepSummary[];
  rankings: RankingResult[] | null;  // council strategy only
  charts: string[] | null;           // base64 PNG strings
  files: string[] | null;            // filenames in session workspace
  strategy_used: string;
}
```

### `ToolCallRecordResponse`
```typescript
{
  id: number;
  tool_name: string;       // "web_search" | "run_code" | "run_shell" | ...
  agent_name: string;
  input_args: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  duration_ms: number | null;
  status: "success" | "error";
  created_at: string;
}
```

### `AgentResponse`
```typescript
{
  id: number;
  name: string;
  endpoint: string;
  model_name: string | null;
  role: "ceo" | "cto" | "cfo" | "planner" | "questioner" | "manager" |
        "hr_manager" | "backend_manager" | "frontend_manager" | "qa_manager" |
        "employee" | "developer" | "tester";
  parent_id: number | null;
  is_orchestrator: boolean;
  is_active: boolean;
  operational_status: "active" | "inactive" | "paused" | "stopped" | "failed";
  infrastructure_status: "online" | "offline";
  state: "idle" | "executing" | "planning" | "delegating" | "waiting" |
         "reporting" | "completed" | "failed" | "stopped";
  temperature: number;
  max_tokens: number;
  context_window_tokens: number;
  capabilities: string[] | null;
  hierarchy_level: number;
  crash_count: number;
  avg_response_time_ms: number | null;
  is_warm: boolean;
  last_heartbeat: string | null;
  created_at: string;
  updated_at: string;
}
```

### `TaskResponse`
```typescript
{
  id: number;
  prompt: string;
  strategy: "sequential" | "parallel" | "dynamic" | "council" | "hierarchical";
  status: "pending" | "running" | "completed" | "failed";
  final_output: string | null;
  task_metadata: StructuredOutput | null;
  steps: TaskStepResponse[];
  created_at: string;
  completed_at: string | null;
}
```

### `LogEntry`
```typescript
{
  id: number;
  task_id: number | null;
  level: "info" | "warning" | "error" | "debug" | "agent";
  source: string;
  message: string;
  timestamp: string;
}
```
