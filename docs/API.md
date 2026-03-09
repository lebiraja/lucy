# Lucy — API Reference

Base URL: `http://localhost:2800` (direct) or `/api` (via nginx proxy at port 2000)

---

## Health & Logs

### `GET /api/health`
Returns system-wide health statistics.

**Response**
```json
{
  "status": "ok",
  "service": "lucy-orchestrator",
  "total_agents": 3,
  "online_agents": 2,
  "active_tasks": 1,
  "completed_tasks": 12,
  "failed_tasks": 1,
  "success_rate": 92,
  "uptime_seconds": 3600
}
```

---

### `GET /api/logs`
Returns the most recent system-wide log entries.

**Query Parameters**
| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 100 | Max entries to return |
| `offset` | int | 0 | Pagination offset |

**Response** — array of `LogEntry`

---

## Agents

### `POST /api/agents`
Register a new LLM agent. Auto-detects `model_name` from the endpoint if not provided. Probes the endpoint to set initial `infrastructure_status`.

**Request Body**
```json
{
  "name": "Aria",
  "endpoint": "http://192.168.73.41:9002",
  "model_name": "llama3.1:70b",     // optional — auto-detected
  "role": "ceo",                     // ceo|cto|manager|employee
  "description": "Lead orchestrator",
  "is_orchestrator": true,
  "temperature": 0.7,
  "max_tokens": 4096,
  "top_p": 0.95,
  "context_window_tokens": 128000,
  "max_iterations": 10,
  "timeout_seconds": 300
}
```

**Response** — `AgentResponse` (see schema below)  
**Status** — `201 Created`

---

### `GET /api/agents`
List all registered agents (ordered by `created_at` descending).

**Response** — array of `AgentResponse`

---

### `GET /api/agents/health`
Run a health check on all active agents in parallel. Updates `infrastructure_status` and `is_warm` in the database.

**Response** — array of `AgentHealth`
```json
[
  {
    "id": 1,
    "name": "Aria",
    "endpoint": "http://192.168.73.41:9002",
    "is_online": true,
    "latency_ms": 42.3,
    "error": null
  }
]
```

---

### `GET /api/agents/hierarchy`
Returns the agent tree structure.

**Response**
```json
[
  {
    "id": 1,
    "name": "Aria",
    "role": "ceo",
    "operational_status": "active",
    "infrastructure_status": "online",
    "state": "idle",
    "is_orchestrator": true,
    "children": [
      { "id": 2, "name": "Nova", "role": "cto", "children": [...] }
    ]
  }
]
```

---

### `GET /api/agents/{id}`
Get a specific agent by ID.

---

### `PUT /api/agents/{id}`
Update agent configuration.

**Request Body** — any subset of `AgentCreate` fields (all optional).

---

### `DELETE /api/agents/{id}`
Remove an agent.  
**Status** — `204 No Content`

---

### `POST /api/agents/{id}/pause`
Set `operational_status = paused`, `state = stopped`.

### `POST /api/agents/{id}/resume`
Set `operational_status = active`, `state = idle`.

### `POST /api/agents/{id}/stop`
Set `operational_status = stopped`, `state = stopped`.

### `GET /api/agents/{id}/health`
Run a health check on a specific agent.

### `POST /api/agents/probe`
Probe a vLLM endpoint before registration to discover available models.

**Request Body**
```json
{ "endpoint": "http://192.168.73.41:9002" }
```

**Response**
```json
{
  "success": true,
  "model_name": "llama3.1:70b",
  "models": ["llama3.1:70b"]
}
```

---

## Tasks

### `POST /api/tasks`
Create and immediately start executing a task.

**Request Body**
```json
{
  "prompt": "Design a microservices architecture for a real-time analytics platform.",
  "strategy": "council",           // sequential|parallel|dynamic|council
  "agent_ids": [1, 2, 3]           // optional — null = all active agents
}
```

**Response** — `TaskResponse` (initial `status: "pending"`)  
**Status** — `201 Created`

The task executes asynchronously. Use `/api/tasks/{id}` or SSE to follow progress.

---

### `GET /api/tasks`
List all tasks with their steps (agents eagerly loaded).

**Query Parameters**
| Param | Type | Default |
|---|---|---|
| `limit` | int | 50 |
| `offset` | int | 0 |

**Response** — array of `TaskResponse`

---

### `GET /api/tasks/{id}`
Get a specific task with all steps and agent information.

---

### `GET /api/tasks/{id}/logs`
Get all log entries associated with a task.

---

### `GET /api/tasks/{id}/events`
**Server-Sent Events** stream for real-time task progress.

**Event format**
```
data: {"level": "info", "source": "orchestrator", "message": "STAGE 1: Collecting opinions...", "task_id": 5, "timestamp": "2026-03-09T10:00:00Z"}

data: {"type": "done", "status": "completed", "task_id": 5}
```

---

## WebSocket

### `WS /api/ws/logs`
Global log stream. Receives all log entries from all tasks and system events as they are written.

### `WS /api/ws/logs/{task_id}`
Task-scoped log stream. Receives only log entries for the specified task.

**Message format** — same as SSE log events (JSON string)

---

## Schema Reference

### `AgentResponse`
```typescript
{
  id: number;
  name: string;
  endpoint: string;
  model_name: string | null;
  role: "ceo" | "cto" | "manager" | "employee";
  parent_id: number | null;
  description: string | null;
  is_active: boolean;
  is_orchestrator: boolean;
  operational_status: "active" | "inactive" | "paused" | "stopped" | "failed";
  infrastructure_status: "online" | "offline";
  state: "idle" | "assigned" | "planning" | "delegating" | "executing" | "waiting" | "reporting" | "completed" | "failed" | "stopped";
  temperature: number;
  max_tokens: number;
  top_p: number;
  context_window_tokens: number;
  max_iterations: number;
  timeout_seconds: number;
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
  strategy: "sequential" | "parallel" | "dynamic" | "council";
  status: "pending" | "running" | "completed" | "failed";
  final_output: string | null;
  task_metadata: CouncilMeta | null;  // populated for council strategy
  steps: TaskStepResponse[];
  created_at: string;
  completed_at: string | null;
}
```

### `CouncilMeta` (task_metadata for council tasks)
```typescript
{
  label_to_agent: Record<string, number>;       // "Response A" → agent_id
  aggregate_rankings: {
    agent_id: number;
    agent_name: string;
    agent_role: string;
    average_rank: number;                        // lower = ranked better by peers
    rankings_count: number;
    label: string;
  }[];
  opinions: { agent_id: number; agent_name: string; agent_role: string; response: string }[];
  reviews: { agent_id: number; agent_name: string; agent_role: string; response: string; parsed_ranking: string[] }[];
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
