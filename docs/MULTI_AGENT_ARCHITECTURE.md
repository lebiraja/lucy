# Lucy — Multi-Agent Communication Architecture

**Current Date:** March 10, 2026  
**Project:** Lucy — Multi-Agent Orchestration Platform  
**Language/Framework:** Python + FastAPI with AsyncIO

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Component Architecture](#3-component-architecture)
4. [Communication Channels](#4-communication-channels)
5. [Multi-Agent Strategies](#5-multi-agent-strategies)
6. [Request-Response Flow](#6-request-response-flow)
7. [Database & Persistence](#7-database--persistence)
8. [Real-Time Updates](#8-real-time-updates)
9. [Council Strategy Deep Dive](#9-council-strategy-deep-dive)
10. [Error Handling & Resilience](#10-error-handling--resilience)

---

## 1. System Overview

Lucy is a **multi-agent orchestration platform** that coordinates multiple LLM agents to solve complex problems through parallel execution, intelligent routing, and synthesis.

### High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Dashboard│  │ TaskList │  │LogViewer │  │ Monitor  │      │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
└────────┼────────────┼─────────────┼──────────────┼─────────────┘
         │            │             │              │
         │ HTTP/REST  │   WebSocket │              SSE Logs
         │            │ (Real-time) │              (Streaming)
         ▼            ▼             ▼              ▼
┌────────────────────────────────────────────────────────────────┐
│               FastAPI Backend (Python + AsyncIO)               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  API Router Layer                         │  │
│  │  ┌────────┐  ┌────────┐  ┌───────┐  ┌──────────────┐   │  │
│  │  │/agents │  │/tasks  │  │/ws    │  │/logs(events)│   │  │
│  │  └────┬───┘  └────┬───┘  └───┬───┘  └──────┬───────┘   │  │
│  └───────┼───────────┼──────────┼─────────────┼────────────┘  │
│          │           │          │             │               │
│  ┌───────▼───────────▼──────────▼─────────────▼────────────┐  │
│  │           Orchestrator Service (Core Logic)             │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Strategy Executors:                                │ │  │
│  │  │ • Sequential  • Parallel  • Dynamic  • Council     │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Agent Pool Manager (Health checks, state tracking)│ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Log Broadcaster (WebSocket pub/sub)               │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│          │
│  ┌───────▼──────────────────────────────────────────────────┐  │
│  │          SQLAlchemy ORM + SQLite/PostgreSQL              │  │
│  │  Tables: agents, tasks, task_steps, logs, rankings      │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
         │
         │ HTTP/AsyncIO
         │ (HTTPX Client Pool)
         ▼
┌────────────────────────────────────────────────────────────────┐
│              OpenRouter API Gateway (LLM Endpoint)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  GPT-5       │  │  Gemini 3    │  │ Claude 4.5   │ (...)   │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend Framework** | FastAPI (Python 3.11+) | Async HTTP API server |
| **Concurrency** | `asyncio.gather()` | Parallel agent execution |
| **HTTP Client** | `httpx` (async) | Non-blocking LLM requests with connection pooling |
| **Database ORM** | SQLAlchemy (async) | Model persistence & transactions |
| **Database** | SQLite / PostgreSQL | Task, agent, and log storage |
| **Real-Time Comms** | WebSocket | Live log streaming to frontend |
| **Server Streaming** | SSE (Server-Sent Events) | Progressive task updates |
| **LLM Access** | OpenRouter API | Unified endpoint for multiple models |
| **Frontend** | React 18 (Vite) | UI for task creation & monitoring |
| **State Mgmt** | AsyncSession (SQLAlchemy) | DB transaction management |

---

## 3. Component Architecture

### Backend Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Application (main.py)                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Lifespan Events (Startup/Shutdown)                      │   │
│  │  • Create DB tables                                      │   │
│  │  • Initialize shared httpx.AsyncClient pool              │   │
│  │  • Reset in-flight tasks from previous crashes           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │
         ├─► routers/agents.py
         │   ├─ POST   /api/agents              (Create agent)
         │   ├─ GET    /api/agents              (List agents)
         │   ├─ GET    /api/agents/{id}         (Get agent detail)
         │   ├─ PUT    /api/agents/{id}         (Update agent)
         │   ├─ DELETE /api/agents/{id}         (Delete agent)
         │   ├─ POST   /api/agents/probe        (Probe vLLM endpoint)
         │   └─ GET    /api/agents/{id}/health (Health check)
         │
         ├─► routers/tasks.py
         │   ├─ POST   /api/tasks               (Create & execute task)
         │   ├─ GET    /api/tasks               (List tasks)
         │   ├─ GET    /api/tasks/{id}          (Get task with steps)
         │   ├─ GET    /api/tasks/{id}/logs     (Stream task logs)
         │   └─ DELETE /api/tasks/{id}          (Cancel/delete task)
         │
         └─► routers/ws.py
             ├─ WebSocket /api/ws/logs          (Global log stream)
             └─ WebSocket /api/ws/logs/{task_id}(Task-specific logs)


┌─────────────────────────────────────────────────────────────────┐
│              Services Layer (services/)                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ orchestrator.py - Core Execution Engine                  │   │
│  │  • execute_task(session, task, agents)                   │   │
│  │  • execute_sequential(session, task, agents)             │   │
│  │  • execute_parallel(session, task, agents)               │   │
│  │  • execute_dynamic(session, task, agents)                │   │
│  │  • execute_council(session, task, agents)                │   │
│  │  • _run_step(task_id, agent, prompt, step_order)         │   │
│  │  • parse_ranking_from_text() [Council rankings]          │   │
│  │  • calculate_aggregate_rankings()  [Council synthesis]   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ llm_client.py - LLM Gateway & HTTP                       │   │
│  │  • chat_completion(endpoint, prompt, model, ...)         │   │
│  │  • check_health(endpoint)                                │   │
│  │  • fetch_model_info(endpoint)                            │   │
│  │  • Shared _http_client (AsyncClient with pooling)        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ logger.py - Log Broadcasting                             │   │
│  │  • log_broadcaster (Pub/Sub for WebSocket clients)       │   │
│  │  • subscribe() / unsubscribe()                           │   │
│  │  • broadcast(message, level, source, task_id)            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│              Database Models (models.py)                         │
│                                                                  │
│  ├─ Agent                                                       │
│  │  ├─ id, name, endpoint, model_name                          │
│  │  ├─ role (CEO, CTO, Manager, Employee)                      │
│  │  ├─ operational_status, infrastructure_status               │
│  │  ├─ metrics: crash_count, avg_response_time_ms              │
│  │  └─ is_active, is_orchestrator, is_warm                     │
│  │                                                              │
│  ├─ Task                                                        │
│  │  ├─ id, prompt, strategy (Sequential/Parallel/Dynamic/Council)
│  │  ├─ status (Pending/Running/Completed/Failed)               │
│  │  ├─ final_output, created_at, started_at, completed_at      │
│  │  └─ relationship: steps (TaskStep list)                     │
│  │                                                              │
│  ├─ TaskStep                                                    │
│  │  ├─ id, task_id, agent_id, order                            │
│  │  ├─ status, response, duration_ms                           │
│  │  ├─ step_label (opinion/review/synthesis)                   │
│  │  └─ relationship: task, agent                               │
│  │                                                              │
│  └─ LogEntry                                                    │
│     ├─ id, task_id, level (Info/Warning/Error/Debug/Agent)     │
│     ├─ message, source, timestamp                              │
│     └─ relationship: task                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Communication Channels

### A. HTTP REST API (Request-Response)

```
┌─────────────────┐
│  Frontend/User  │
└────────┬────────┘
         │
         │ HTTP POST /api/tasks
         │ {
         │   "prompt": "...",
         │   "strategy": "council",
         │   "agent_ids": [1, 2, 3]
         │ }
         │
         ▼
┌────────────────────────────────────────────┐
│  FastAPI Task Router (async handler)       │
│  1. Create Task in DB (PENDING)            │
│  2. Launch async _run_task_background()    │
│  3. Return 200 + task_id immediately       │
└────────────────────────────────────────────┘
         │
         │ Returns immediately:
         │ {
         │   "id": 123,
         │   "status": "pending",
         │   "prompt": "...",
         │   "created_at": "2026-03-10..."
         │ }
         │
         ▼
┌────────────────────────────────────────────┐
│  Frontend polls /api/tasks/123 (via hook)  │
│  to get task.status updates                │
└────────────────────────────────────────────┘
```

### B. WebSocket (Real-Time Log Streaming)

```
┌──────────────────────────────────────────┐
│         Frontend (React Component)        │
│  useWebSocket('/api/ws/logs/{task_id}')  │
└──────────────┬───────────────────────────┘
               │
               │ (1) WebSocket upgrade
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│  Router: /api/ws/logs/{task_id}                          │
│  (fastapi.WebSocket handler)                             │
│                                                          │
│  (1) await websocket.accept()                            │
│  (2) queue = log_broadcaster.subscribe(task_id=task_id)  │
│  (3) Loop: await queue.get() → await websocket.send()   │
└──────────────────────────────────────────────────────────┘
         ▲
         │ (Background in orchestrator._log())
         │
┌──────────────────────────────────────────────────────────┐
│  Orchestrator Service (Background Task)                  │
│                                                          │
│  Each time _log() is called:                             │
│  (1) Write LogEntry to database                          │
│  (2) await log_broadcaster.broadcast(                    │
│        message=msg,                                      │
│        task_id=task_id,                                  │
│        level=level,                                      │
│        source=source                                     │
│      )                                                   │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  LogBroadcaster (Pub/Sub)                                │
│                                                          │
│  _subscriptions = {                                      │
│    'global': [queue1, queue2, ...],  (all logs)         │
│    'task:123': [queue3, ...]         (task-specific)    │
│  }                                                       │
│                                                          │
│  broadcast() → put message on all matching queues        │
└──────────────────────────────────────────────────────────┘
         │
         ▼ JSON message
┌────────────────────────────────────────┐
│  Frontend receives over WebSocket:     │
│  {                                     │
│    "message": "Stage 1 complete...",  │
│    "level": "info",                    │
│    "source": "orchestrator",           │
│    "task_id": 123,                     │
│    "timestamp": "2026-03-10T..."       │
│  }                                     │
└────────────────────────────────────────┘
```

### C. LLM Gateway (Async HTTP to OpenRouter)

```
┌──────────────────────────────────────┐
│  _run_step() in Orchestrator          │
│  Needs to call an agent               │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│  llm_client.chat_completion()                            │
│                                                          │
│  Takes: endpoint, model_name, prompt, token_limits      │
│  Returns: text response                                 │
└──────────┬───────────────────────────────────────────────┘
           │
           │ Uses shared httpx.AsyncClient pool
           │ (initialized in FastAPI lifespan)
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│  OpenRouter API (https://openrouter.io/api/v1/chat...)  │
│                                                          │
│  Endpoint: POST /chat/completions                        │
│  Model: "openai/gpt-5", "google/gemini-3-pro", etc.    │
│  Auth: Bearer {OPENROUTER_API_KEY}                       │
│                                                          │
│  Returns: {"choices": [{"message": {"content": "..."}}]} │
└───────────┬───────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────┐
│  Response text + metadata             │
│  (latency in ms, token count, etc.)   │
└──────────────────────────────────────┘
```

---

## 5. Multi-Agent Strategies

Lucy supports **4 distinct multi-agent communication patterns:**

### Strategy 1: SEQUENTIAL

```
User Query
    │
    ▼
┌─────────────────┐
│   Agent 1       │  Prompt: User query
│   (Model A)     │  Output: Response A
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Agent 2       │  Prompt: "User query + Response A above"
│   (Model B)     │  Output: Response B
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Agent 3       │  Prompt: "User query + Response B above"
│   (Model C)     │  Output: Response C
└────────┬────────┘
         │
         ▼
    Final (C)
```

**Code:** `orchestrator.execute_sequential()`  
**Use Case:** Iterative refinement, build on previous answers  
**Communication:** One-directional chain, synchronous

---

### Strategy 2: PARALLEL

```
User Query
    │
    ├─────────────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌─────────────┐                   ┌──────────────┐
│  Agent 1    │                   │   Agent 2    │
│  (asyncio)  │ (concurrent)      │  (asyncio)   │
└────┬────────┘                   └──────┬───────┘
     │                                  │
     │         Parallel Fan-Out         │
     │         (asyncio.gather)         │
     │                                  │
     └──────────────┬────────────────────┘
                    │
                    ▼
        ┌────────────────────────┐
        │   Synthesisor Agent    │
        │   (Orchestrator or CEO)│
        │   Aggregates 2 answers │
        │   into 1 final answer  │
        └────────────────────────┘
                    │
                    ▼
              Final Synthesis
```

**Code:** `orchestrator.execute_parallel()` then `_run_step()` with synthesizer  
**Use Case:** Multiple expert opinions, then consensus  
**Communication:** Fan-out then fan-in; gather results asynchronously

---

### Strategy 3: DYNAMIC

```
User Query
    │
    ▼
┌──────────────────────────────┐
│   Orchestrator Agent         │
│   (Decides routing)          │
│                              │
│  "Given this query,          │
│   use agents [2,1,3]         │
│   in sequential order."      │
└───────────┬──────────────────┘
            │
            │ Decision:
            │ agent_ids: [2, 1, 3]
            │ strategy: "sequential"
            │
            ▼
┌───────────────────────────────────────────┐
│  Execute Based on Decision                │
│  ┌──────┐     ┌──────┐      ┌──────┐    │
│  │Agent2│ --> │Agent1│  --> │Agent3│    │
│  │(CTO) │     (CEO)  │      (Eng)  │    │
│  └──────┘     └──────┘      └──────┘    │
└───────────────────────────────────────────┘
            │
            ▼
        Final Output
```

**Code:** `orchestrator.execute_dynamic()`  
**Use Case:** Complex tasks where routing depends on query analysis  
**Communication:** First, query orchestrator; then execute based on response

---

### Strategy 4: COUNCIL (Most Complex)

```
┌───────────────────────────────────────────────────────────────────┐
│               STAGE 1: Independent Opinions (Parallel)             │
│                                                                    │
│  User Query                                                        │
│     │                                                              │
│     │  (asyncio.gather all agents concurrently)                   │
│     │                                                              │
│     ├────────────────────────┬─────────────────────┬──────────┐   │
│     │                        │                     │          │   │
│     ▼                        ▼                     ▼          ▼   │
│  ┌────────┐            ┌────────┐          ┌────────┐    ┌────────┐
│  │ Agent1 │            │ Agent2 │          │ Agent3 │    │ Agent4 │
│  │  (CEO) │            │ (CTO)  │          │(Mgr)   │    │ (Eng)  │
│  └────┬───┘            └────┬───┘          └────┬───┘    └────┬───┘
│       │ Opinion 1           │ Opinion 2         │ Opinion 3     │ Opinion 4
│       └──────────────────────┼─────────────────┼────────────┬──┘
│                              │                             │
└──────────────────────────────┼────────────────────────────┘
                               │
┌──────────────────────────────┼────────────────────────────┐
│            STAGE 2: Anonymous Peer Review (Parallel)     │
│                                                           │
│  Anonymized Opinions:                                    │
│  ┌─────────────────────┐                                │
│  │ Response A (unknown)│                                │
│  │ Response B (unknown)│ ◄─ Shown to all reviewers      │
│  │ Response C (unknown)│     without author names       │
│  │ Response D (unknown)│                                │
│  └─────────────────────┘                                │
│                                                           │
│  Each agent ranks them: "Best: Response X, then Y, Z"    │
│     │                                                     │
│     ├────────────────────────┬─────────────────────┬──┐   │
│     │                        │                     │  │   │
│     ▼                        ▼                     ▼  ▼   │
│  ┌────────┐            ┌────────┐          ┌────────────┐
│  │ Review │            │ Review │          │   Rank     │
│  │   1    │            │   2    │          │    (All)   │
│  │"A,C,   │            │"C,A,   │          │            │
│  │ D,B"   │            │ B,D"   │          │            │
│  └────┬───┘            └────┬───┘          └────┬───────┘
│       │                     │                   │
└───────┼─────────────────────┼───────────────────┴─────────┐
        │                     │
        │ All reviews collected
        │
┌───────▼─────────────────────▼───────────────────────────┐
│       STAGE 3: CEO Synthesis (Named Context)            │
│                                                          │
│  Orchestrator Agent (CEO) reads:                        │
│  • Original opinions (now with names revealed)          │
│  • All peer rankings                                    │
│  • Aggregate scores                                     │
│                                                          │
│  Output: Synthesized final answer incorporating:        │
│  • Consensus points                                     │
│  • Divergent perspectives                              │
│  • Ranked evidence hierarchy                           │
└───────┬──────────────────────────────────────────────────┘
        │
        ▼
   Final Answer
```

**Code:**  
- Stage 1: `orchestrator.execute_council()` → `asyncio.gather(get_opinion(...))`
- Stage 2: Anonymous labels (A, B, C, D) → `asyncio.gather(review_anonymous(...))`
- Stage 3: `parse_ranking_from_text()` → `calculate_aggregate_rankings()` → CEO synthesis

**Use Case:** High-stakes decisions, complex analysis, academic-style peer review  
**Communication:** 3-phase: parallel opinions → anonymous review → named synthesis

---

## 6. Request-Response Flow

### Complete Task Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ USER / FRONTEND                                                 │
└──────────┬──────────────────────────────────────────────────────┘
           │
           │ POST /api/tasks
           │ {
           │   "prompt": "Should we migrate to microservices?",
           │   "strategy": "council",
           │   "agent_ids": [1, 2, 3, 4]
           │ }
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│ FASTAPI BACKEND - routers/tasks.py::create_task()              │
│                                                                 │
│ (1) Validate input (TaskCreate schema)                          │
│ (2) Query agents from DB                                        │
│ (3) Create Task record in DB:                                  │
│     status = PENDING, strategy = COUNCIL                        │
│ (4) Launch async background task:                              │
│     _run_task_background(task_id, agent_ids)                   │
│ (5) RETURN 201 + {id, status: PENDING, ...}                    │
└──────────┬──────────────────────────────────────────────────────┘
           │
           │ Response
           │ {
           │   "id": 123,
           │   "status": "pending",
           │   "created_at": "2026-03-10T...",
           │   "steps": []
           │ }
           │
           ▼
┌─────────────────────────────────┐   ┌──────────────────────────┐
│ Frontend receives task_id: 123  │   │ Background Task Executes │
│                                 │   │ (_run_task_background)   │
│ Sets up WebSocket listener      │   │                          │
│ to /api/ws/logs/123             │   │ (1) Acquires DB session  │
│                                 │   │ (2) Calls execute_task() │
│                                 │   │ (3) Updates task.status  │
└─────────────────────────────────┘   └──────────┬───────────────┘
           ▲                                      │
           │                          ┌───────────▼──────────────┐
           │                          │ Orchestrator Service:    │
           │                          │ execute_council()        │
           │                          │                          │
           │                          │ STAGE 1:                 │
           │                          │ ┌──────────────────────┐ │
           │                          │ │ asyncio.gather(      │ │
           │                          │ │  get_opinion(a1),    │ │
           │                          │ │  get_opinion(a2),    │ │
           │                          │ │  get_opinion(a3),    │ │
           │                          │ │  get_opinion(a4)     │ │
           │                          │ │ )                    │ │
           │                          │ └──────────┬───────────┘ │
           │                          │            │              │
           │                          │ For each opinion:         │
           │                          │ (call _run_step)         │
           │                          │ → HTTP POST to OpenRouter│
           │                          │                          │
           │                          │ STAGE 2:                 │
           │                          │ ┌──────────────────────┐ │
           │                          │ │ Anonymize opinions   │ │
           │                          │ │ Assign labels: A,B...│ │
           │                          │ │ asyncio.gather(      │ │
           │                          │ │  review_anonymous()  │ │
           │                          │ │ )                    │ │
           │                          │ └──────────┬───────────┘ │
           │                          │            │              │
           │                          │ Parse rankings from      │
           │                          │ review responses         │
           │                          │                          │
           │                          │ STAGE 3:                 │
           │                          │ ┌──────────────────────┐ │
           │                          │ │ CEO reads all        │ │
           │                          │ │ opinions + rankings   │ │
           │                          │ │ Synthesize final ans  │ │
           │                          │ │ _run_step(ceo_agent) │ │
           │                          │ └──────────┬───────────┘ │
           │                          └────────────┼──────────────┘
           │                                       │
           │ Each _log() call:                     │
           │ (1) Write LogEntry to DB             │
           │ (2) log_broadcaster.broadcast()      │
           │                                       │
           │◄──────────────────────────────────────┘
           │
           │ WebSocket message received:
           │ {
           │   "message": "Stage 1: Collecting opinions...",
           │   "level": "info",
           │   "source": "orchestrator",
           │   "task_id": 123
           │ }
           │
           ▼
┌────────────────────────────────────────────┐
│ Frontend Component Updates Logs             │
│ <LogViewer client-side state: [...msgs]>   │
│ Progress bar shows "Stage 1..."             │
└────────────────────────────────────────────┘


At Task Completion:
┌────────────────────────────────────────────┐  ┌────────────────────┐
│ Update Task Record:                         │  │ Final log message  │
│ task.status = COMPLETED                    │  │ "Council complete" │
│ task.final_output = "<synthesized answer>" │  └────────────────────┘
│ task.completed_at = now()                  │
│ Flush to DB                                │
└────────────────────────────────────────────┘
         │
         │
         ▼
┌─────────────────────────────────────┐
│ Frontend polls /api/tasks/123       │
│ Detects status = COMPLETED          │
│ Displays final_output to user       │
└─────────────────────────────────────┘
```

---

## 7. Database & Persistence

### Entity Relationships

```
Task (1) ──────────────► (Many) TaskStep
│                            │
│                            ├─ Agent -> {FK: agent_id}
│                            ├─ Status (PENDING/RUNNING/COMPLETED/FAILED)
│                            └─ Response (LLM output)
│
├─ Status (PENDING/RUNNING/COMPLETED/FAILED)
├─ Strategy (SEQUENTIAL/PARALLEL/DYNAMIC/COUNCIL)
├─ Prompt
├─ final_output
└─ Timestamps (created, started, completed)


Task (1) ──────────────► (Many) LogEntry
                             │
                             ├─ Level (INFO/WARNING/ERROR/DEBUG/AGENT)
                             ├─ Message
                             ├─ Source (agent name or orchestrator)
                             └─ Timestamp


Agent (1) ◄────────────── (Many) TaskStep
│
├─ Endpoint (http://localhost:9002)
├─ Model Name (gpt-5, gemini-3, etc.)
├─ Role (CEO/CTO/MANAGER/EMPLOYEE)
├─ Status (ACTIVE/INACTIVE/PAUSED/STOPPED/FAILED)
├─ State (IDLE/ASSIGNED/PLANNING/EXECUTING/COMPLETED)
├─ Metrics (response_time_ms, crash_count)
└─ Flags (is_active, is_orchestrator, is_warm)
```

### Schema Details

```sql
CREATE TABLE agents (
  id              INTEGER PRIMARY KEY,
  name            VARCHAR(255) UNIQUE NOT NULL,
  endpoint        VARCHAR(512) NOT NULL,         -- vLLM or OpenRouter
  model_name      VARCHAR(255),                   -- auto-detected
  description     TEXT,
  role            ENUM(ceo, cto, manager, employee),
  operational_status ENUM(active, inactive, paused, stopped, failed),
  infrastructure_status ENUM(online, offline),
  state           ENUM(idle, assigned, planning, executing, completed, failed),
  is_active       BOOLEAN DEFAULT TRUE,
  is_orchestrator BOOLEAN DEFAULT FALSE,
  is_warm         BOOLEAN DEFAULT FALSE,
  response_time_ms FLOAT,
  crash_count     INTEGER DEFAULT 0
);

CREATE TABLE tasks (
  id              INTEGER PRIMARY KEY,
  prompt          TEXT NOT NULL,
  strategy        ENUM(sequential, parallel, dynamic, council),
  status          ENUM(pending, running, completed, failed),
  final_output    TEXT,
  created_at      TIMESTAMP,
  started_at      TIMESTAMP,
  completed_at    TIMESTAMP
);

CREATE TABLE task_steps (
  id              INTEGER PRIMARY KEY,
  task_id         INTEGER FOREIGN KEY,
  agent_id        INTEGER FOREIGN KEY,
  order           INTEGER,
  status          ENUM(pending, running, completed, failed),
  response        TEXT,
  duration_ms     FLOAT,
  step_label      VARCHAR(50)    -- 'opinion', 'review', 'synthesis'
);

CREATE TABLE log_entries (
  id              INTEGER PRIMARY KEY,
  task_id         INTEGER FOREIGN KEY,
  level           ENUM(info, warning, error, debug, agent),
  message         TEXT,
  source          VARCHAR(100),  -- agent name or 'orchestrator'
  timestamp       TIMESTAMP
);
```

---

## 8. Real-Time Updates

### WebSocket Pub/Sub Pattern

```
┌──────────────────────────────────────────────────────────┐
│  Multiple Frontend Clients (React Components)            │
│                                                          │
│  Client A: /api/ws/logs/123    (task-specific)          │
│  Client B: /api/ws/logs        (global)                 │
│  Client C: /api/ws/logs/456    (different task)         │
└────────────────┬──────────────────────────────────────────┘
                 │
                 │ WebSocket connections
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI WebSocket Handlers (routers/ws.py)             │
│                                                          │
│  @router.websocket("/api/ws/logs/{task_id}")             │
│  async def websocket_task_logs(ws, task_id):             │
│      while True:                                         │
│          queue = subscribe(task_id=task_id)              │
│          msg = await queue.get()                         │
│          await ws.send_text(msg)                         │
└────────────────┬──────────────────────────────────────────┘
                 │
                 │ Feeding from
                 │
┌────────────────▼──────────────────────────────────────────┐
│  LogBroadcaster (Pub/Sub Manager)                        │
│                                                          │
│  _subscriptions = {                                      │
│    'global': [queue1, queue2, queue3],                  │
│    'task:123': [queue_a, queue_b],                       │
│    'task:456': [queue_c]                                 │
│  }                                                       │
│                                                          │
│  subscribe(task_id=123) → new_queue                      │
│  broadcast(message, task_id=123) →                       │
│    put message on all queues in 'task:123' AND 'global'  │
└────────────────┬──────────────────────────────────────────┘
                 │
                 │ Fed by
                 │
┌────────────────▼──────────────────────────────────────────┐
│  Orchestrator (Background Task Execution)                │
│                                                          │
│  async def _log(task_id, message, level, source):        │
│      # (1) Persist to DB                                 │
│      entry = LogEntry(task_id, level, message, source)   │
│      session.add(entry)                                  │
│      await session.commit()                              │
│                                                          │
│      # (2) Broadcast to all subscribers                  │
│      await log_broadcaster.broadcast(                    │
│        message=message,                                  │
│        level=level,                                      │
│        source=source,                                    │
│        task_id=task_id                                   │
│      )                                                   │
└────────────────────────────────────────────────────────────┘
```

### Message Flow Example

```
┌─ Event: Agent 1 Opinion Collected ─────────────────┐
│                                                     │
│ Orchestrator._run_step() returns successfully      │
│ ↓                                                   │
│ await _log(                                        │
│   task_id=123,                                     │
│   message="[CEO Agent] responded in 2345ms",       │
│   level="agent",                                   │
│   source="CEO Agent"                               │
│ )                                                  │
│                                                     │
└─────────────────────────────────────────────────────┘
            │
            ▼
┌─ LogEntry Created & Persisted ───────────────────┐
│                                                   │
│ INSERT INTO log_entries VALUES (                 │
│   id=999,                                        │
│   task_id=123,                                   │
│   level='agent',                                 │
│   message='[CEO Agent] responded in 2345ms',     │
│   source='CEO Agent',                            │
│   timestamp='2026-03-10T14:32:15Z'               │
│ )                                                │
│                                                   │
└─────────────────────────────────────────────────────┘
            │
            ▼
┌─ Broadcast to Subscribers ──────────────────────┐
│                                                 │
│ log_broadcaster.broadcast(                      │
│   message="[CEO Agent] responded in 2345ms",    │
│   level="agent",                                │
│   source="CEO Agent",                           │
│   task_id=123                                   │
│ )                                               │
│                                                 │
│ → Convert to JSON:                              │
│ {                                               │
│   "message": "[CEO Agent] responded...",        │
│   "level": "agent",                             │
│   "source": "CEO Agent",                        │
│   "task_id": 123,                               │
│   "timestamp": "2026-03-10T14:32:15Z"           │
│ }                                               │
│                                                 │
│ → Put on queues:                                │
│   - 'global' subscribers get it                 │
│   - 'task:123' subscribers get it               │
│                                                 │
└─────────────────────────────────────────────────────┘
            │
            ▼
┌─ WebSocket Send to Clients ─────────────────────┐
│                                                 │
│ Client A (listening to task:123):               │
│   await websocket.send_text(json_message)       │
│                                                 │
│ Client B (listening to global):                 │
│   await websocket.send_text(json_message)       │
│                                                 │
│ Client C (listening to different task):         │
│   [message NOT sent]                            │
│                                                 │
└─────────────────────────────────────────────────────┘
            │
            ▼
┌─ Frontend React Component Update ──────────────┐
│                                                 │
│ const { logs } = useWebSocket(                 │
│   '/api/ws/logs/123'                            │
│ )                                               │
│                                                 │
│ setState(prev => [...prev, newLogEntry])       │
│ ↓ Component re-renders                          │
│ <div className="log-viewer">                    │
│   {logs.map(log => (                            │
│     <LogLine key={...} log={log} />             │
│   ))}                                           │
│ </div>                                          │
│                                                 │
└─────────────────────────────────────────────────────┘
```

---

## 9. Council Strategy Deep Dive

The **Council pattern** mirrors human expert committees and academic peer review:

### Stage 1: Independent Opinions

```
Input: Single system prompt (with role flavoring)
       + Original user question

4 Agents (running in parallel via asyncio.gather):
  ┌─ Agent 1 (CEO)
  │  System Prompt: "You are a C-level executive..."
  │  + User Query
  │  → Opinion 1
  │
  ├─ Agent 2 (CTO)
  │  System Prompt: "You are a CTO with deep technical..."
  │  + User Query
  │  → Opinion 2
  │
  ├─ Agent 3 (Manager)
  │  System Prompt: "You are a Project Manager..."
  │  + User Query
  │  → Opinion 3
  │
  └─ Agent 4 (Engineer)
     System Prompt: "You are a software engineer..."
     + User Query
     → Opinion 4

Each query: _run_step(task_id, agent, prompt, step_order=0-3, step_label="opinion")
  → HTTP POST to OpenRouter
  → Store in DB: TaskStep with response
  → Broadcast log message
```

### Stage 2: Anonymous Peer Review

```
Input: Anonymized opinions (labeled Response A, B, C, D)
       WITHOUT agent names or roles revealed

All 4 agents review all opinions (parallel via asyncio.gather):

┌─ Agent 1 (reviewing anonymously)
│  Prompt: "Here are 4 responses. Rank them best to worst.
│           FINAL RANKING: 1. Response X, 2. Response Y, ..."
│  → ranking = ["Response C", "Response A", "Response D", "Response B"]
│
├─ Agent 2 (reviewing anonymously)
│  Same anonymized block
│  → ranking = ["Response A", "Response C", "Response B", "Response D"]
│
├─ Agent 3 (reviewing anonymously)
│  Same anonymized block
│  → ranking = ["Response B", "Response A", "Response C", "Response D"]
│
└─ Agent 4 (reviewing anonymously)
   Same anonymized block
   → ranking = ["Response D", "Response B", "Response A", "Response C"]

Parse each ranking using parse_ranking_from_text():
  • Extract "FINAL RANKING:" section
  • Find numbered list OR any mention of "Response X"
  • Return ordered list

Aggregate rankings using calculate_aggregate_rankings():
  • Assign position points: 1st place = position 1, 2nd = position 2, etc.
  • Average position per agent
  • Agent with lowest average = ranked highest
```

### Stage 3: CEO Synthesis

```
Input: All opinions (now with author names)
     + Aggregated ranking scores
     + Full peer reviews

CEO Agent (special role) generates synthesis:

Prompt includes:
  • Original user question
  • All 4 opinions with author names + roles
  • All peer reviews (with names)
  • Aggregate ranking showing consensus
  
CEO synthesizes into final answer that:
  → Incorporates consensus points
  → Notes divergent perspectives with reasoning
  → Uses ranked evidence (most-agreed-upon items highlighted)

Output: Final single answer
        (returned to user as task.final_output)
```

---

## 10. Error Handling & Resilience

### Failure Scenarios

```
┌─ Network Failure (LLM Endpoint Down) ─────────────┐
│                                                   │
│ _run_step() → chat_completion() → httpx error    │
│                                                   │
│ CATCH:                                            │
│   - Log error with level="error"                  │
│   - Record step.status = FAILED                   │
│   - Orchestrator evaluates strategy:              │
│     - Sequential: Stop chain, mark task FAILED    │
│     - Parallel: Skip agent, continue with others  │
│     - Council: If main agents fail, partial      │
│       council (fewer participants)               │
│                                                   │
└───────────────────────────────────────────────────┘

┌─ Timeout (Agent Takes Too Long) ───────────────────┐
│                                                    │
│ llm_client timeout = 120 seconds (configurable)   │
│                                                    │
│ CATCH:                                             │
│   - AsyncClient.timeout fires                     │
│   - Same error handling as network failure        │
│   - Log includes timeout duration                 │
│                                                    │
└────────────────────────────────────────────────────┘

┌─ Database Transaction Failure ──────────────────────┐
│                                                     │
│ Task execution in session.commit() fails           │
│                                                     │
│ CATCH (in _run_task_background):                   │
│   (1) session.rollback()                           │
│   (2) Attempt recovery: create new session       │
│   (3) Mark task.status = FAILED                    │
│   (4) Log final error and flush                    │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─ Server Restart (In-Flight Tasks) ──────────────────┐
│                                                      │
│ FastAPI lifespan startup event:                     │
│   FOR each task IN (PENDING, RUNNING):              │
│     UPDATE task.status = FAILED                     │
│     SET final_output = "Server restarted..."        │
│                                                      │
│ Prevents orphaned tasks in limbo state              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Agent Health Tracking

```
For each agent:
  • track operational_status (ACTIVE/INACTIVE/FAILED)
  • track infrastructure_status (ONLINE/OFFLINE)
  • increment crash_count on errors
  • track avg_response_time_ms (exponential moving average)
  • flag is_warm = True after successful response

Queries filter agents by:
  is_active = True
  AND operational_status = ACTIVE
  AND infrastructure_status = ONLINE

Failed agents excluded from future tasks until manually reactivated
```

---

## Summary Table: Communication Methods

| Method | Direction | Real-Time? | Use Case | Layer |
|--------|-----------|-----------|----------|-------|
| **HTTP REST API** | Request-Response | No (polling) | CRUD operations, task creation | HTTP |
| **WebSocket** | Bi-directional | Yes | Log streaming, progress updates | WebSocket |
| **AsyncIO (Internal)** | Function calls | Yes | Parallel agent execution | Python |
| **HTTPX (Async)** | HTTP | Sync-over-async | LLM queries | HTTP Client |
| **Database (SQLAlchemy)** | Transactional | N/A | Persistence, transactions | SQL |

---

## Architecture Evolution

```
Current (v1.0):
  Single FastAPI server
  + Async orchestrator
  + 4 strategies (Sequential, Parallel, Dynamic, Council)
  + Local SQLite/PostgreSQL
  + WebSocket for logs

Future Scaling (v2.0):
  • Separate orchestrator as dedicated microservice
  • Message queue (RabbitMQ/RedisPubSub) for task distribution
  • Multi-server deployment with load balancer
  • Distributed session management
  • Advanced scheduling (Celery/APScheduler)
```

---

## Key Design Decisions

1. **AsyncIO over threading**: Better resource utilization for I/O-bound LLM calls
2. **Shared httpx.AsyncClient pool**: Connection pooling avoids per-request overhead
3. **WebSocket pub/sub**: Real-time updates without polling; scalable with many clients
4. **3-Stage Council pattern**: Mirrors human expertise; anonymous review improves objectivity
5. **Background task execution**: Immediate API response; task runs in background
6. **DB-driven state**: Single source of truth for task/step data
7. **Role-aware prompts**: Council members think from different perspectives
8. **Aggregate ranking algorithm**: Consensus-based scoring across peers
