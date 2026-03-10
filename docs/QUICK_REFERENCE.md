# Lucy — Multi-Agent Communication: Quick Reference

A cheat sheet for understanding how Lucy's multi-agent system communicates.

---

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│  TECHNOLOGY STACK MATRIX                                    │
└─────────────────────────────────────────────────────────────┘

LAYER                   TECHNOLOGY              ROLE
─────────────────────────────────────────────────────────────
Backend Core            FastAPI (Python)        Async HTTP API
Concurrency             asyncio.gather()        Parallel execution
HTTP Client             httpx (async)           LLM requests
Database ORM            SQLAlchemy Async        Model persistence
Database                SQLite/PostgreSQL       Data storage
Real-Time (Push)        WebSocket               Live log streaming
Real-Time (Server)      SSE                     Streaming responses
LLM Access              OpenRouter API          Unified LLM gateway
Frontend                React 18 (Vite)         UI for task management
Schema Validation       Pydantic                Request validation
State Management        AsyncSession            DB transactions
Connection Pooling      httpx Limits            Prevent exhaustion
Pub/Sub Pattern         asyncio.Queue           Log broadcasting
┌─────────────────────────────────────────────────────────────┐
```

---

## Communication Channels

### Channel 1: HTTP REST API (Request-Response)

```
┌──────────────────────────────────────────────────────────┐
│ HTTP REST API                                            │
├──────────────────────────────────────────────────────────┤
│ Pattern:        Request-Response                         │
│ Real-Time?:     No (polling required)                    │
│ Protocol:       HTTP/1.1 or HTTP/2                       │
│ Format:         JSON                                      │
│ Endpoints:                                               │
│                                                          │
│  POST   /api/tasks              Create & execute task    │
│  GET    /api/tasks              List all tasks           │
│  GET    /api/tasks/{id}         Get task detail          │
│  GET    /api/tasks/{id}/logs    Streaming logs (SSE)    │
│  DELETE /api/tasks/{id}         Cancel task              │
│                                                          │
│  POST   /api/agents             Register new agent       │
│  GET    /api/agents             List agents              │
│  PUT    /api/agents/{id}        Update agent             │
│  DELETE /api/agents/{id}        Deactivate agent         │
│  GET    /api/agents/{id}/health Health check             │
└──────────────────────────────────────────────────────────┘
```

### Channel 2: WebSocket (Bidirectional Real-Time)

```
┌──────────────────────────────────────────────────────────┐
│ WebSocket                                                │
├──────────────────────────────────────────────────────────┤
│ Pattern:        Bidirectional (server push)              │
│ Real-Time?:     YES (push from server)                   │
│ Protocol:       WebSocket (ws/wss)                       │
│ Format:         JSON                                      │
│ Endpoints:                                               │
│                                                          │
│  ws /api/ws/logs              Global log stream          │
│  ws /api/ws/logs/{task_id}    Task-specific logs         │
│                                                          │
│ Pub/Sub Model:                                           │
│  • Subscribe to 'global' or 'task:{id}' channel         │
│  • Receive JSON messages in real-time                    │
│  • Message format:                                       │
│    {                                                     │
│      "message": "...",                                   │
│      "level": "info|warning|error|debug|agent",         │
│      "source": "agent_name|orchestrator",               │
│      "task_id": 123,                                     │
│      "timestamp": "2026-03-10T14:32:15Z"                │
│    }                                                     │
└──────────────────────────────────────────────────────────┘
```

### Channel 3: Internal Async HTTP (Python-to-LLM)

```
┌──────────────────────────────────────────────────────────┐
│ Internal Async HTTP (httpx)                              │
├──────────────────────────────────────────────────────────┤
│ Pattern:        HTTP requests (async)                    │
│ Real-Time?:     Concurrent (not sequential)              │
│ Protocol:       HTTP/1.1 with connection pooling         │
│ Format:         JSON                                      │
│ Target:         OpenRouter API (LLM gateway)             │
│                                                          │
│ Features:                                                │
│  • Shared connection pool (max_connections=100)          │
│  • Keep-alive connections (max_keepalive=20)             │
│  • Timeout: 120 seconds per request                      │
│  • Non-blocking (integrates with asyncio)                │
│                                                          │
│ Example Call:                                            │
│  response = await httpx_client.post(                     │
│      "https://api.openrouter.io/api/v1/chat/completions",│
│      json=payload,                                       │
│      headers={...},                                      │
│      timeout=120                                         │
│  )                                                       │
└──────────────────────────────────────────────────────────┘
```

### Channel 4: Database (SQLAlchemy ORM)

```
┌──────────────────────────────────────────────────────────┐
│ Database (SQLAlchemy Async ORM)                          │
├──────────────────────────────────────────────────────────┤
│ Pattern:        Transactional SQL                        │
│ Real-Time?:     No (async writes)                        │
│ Protocol:       SQL (SQLite/PostgreSQL)                  │
│ Format:         Relational tables                        │
│                                                          │
│ Key Tables:                                              │
│  • agents           (Agent configuration & metrics)      │
│  • tasks            (Task configuration & status)        │
│  • task_steps       (Execution steps within tasks)       │
│  • log_entries      (Audit trail & debugging)            │
│                                                          │
│ Usage Pattern:                                           │
│  async with AsyncSession(engine) as session:             │
│      query = select(Task).where(Task.id == 123)          │
│      result = await session.execute(query)               │
│      task = result.scalar_one_or_none()                  │
│      await session.commit()                              │
└──────────────────────────────────────────────────────────┘
```

---

## Communication Flows by Strategy

### SEQUENTIAL Strategy

```
User Query
    │
    ▼ (Agent 1)
[=========] Response 1  (Takes ~250ms)
    │
    ▼ (Agent 2, sees Response 1)
[=========] Response 2  (Takes ~300ms)
    │
    ▼ (Agent 3, sees Responses 1+2)
[=========] Response 3  (Takes ~280ms)
    │
    ▼ Total: ~830ms (serial, no parallelism)
Final Output: Response 3
```

**Use Case:** Iterative refinement, build on context  
**Communication:** One→One→One chain  
**Total Time:** Sum of all agent times  

---

### PARALLEL Strategy

```
User Query
    │
    ├─────▶ Agent 1 [=======] Response 1  (250ms)
    │                                  │
    ├─────▶ Agent 2 [=======] Response 2  (300ms) (parallel execution)
    │                                  │
    └─────▶ Agent 3 [=======] Response 3  (280ms)
    │
    ▼ ~300ms max (not 830ms)
    │
    ▼ Synthesizer sees all 3
[===========] Final Synthesis (400ms)
    │
    ▼ Total: ~700ms (700ms faster!)
Final Output: Synthesis of 1+2+3
```

**Use Case:** Multiple expert opinions → consensus  
**Communication:** One→Many→One  
**Total Time:** Max(all agents) + synthesis time  

---

### DYNAMIC Strategy

```
User Query
    │
    ▼ Orchestrator analyzes query
    │ "This needs: [Agent 2, Agent 1, Agent 3] sequential"
    │
    ▼ Decision routing: sub_strategy, agent_ids, reasoning
    │
    ├─ EXECUTE based on decision (Sequential or Parallel)
    │
    ▼ Final Output
```

**Use Case:** Complex queries needing intelligent routing  
**Communication:** Orchestrator→Query→Execute  
**Total Time:** Routing (~100ms) + strategy execution time  

---

### COUNCIL Strategy (Most Complex)

```
STAGE 1: Opinions (Parallel, ~300ms max)
    │
    ├──▶ Agent A [=====] Opinion A  (250ms, CEO role)
    ├──▶ Agent B [=====] Opinion B  (300ms, CTO role)
    ├──▶ Agent C [=====] Opinion C  (280ms, Mgr role)
    └──▶ Agent D [=====] Opinion D  (270ms, Eng role)
    │
    ▼ ~300ms elapsed

STAGE 2: Anonymous Review (Parallel, ~350ms max)
    │ [Anonymize: Response A, B, C, D — no names shown]
    │
    ├──▶ Agent A ranks [=====' ] Ranking 1  (350ms, blind)
    ├──▶ Agent B ranks [=====' ] Ranking 2  (340ms, blind)
    ├──▶ Agent C ranks [=====' ] Ranking 3  (360ms, blind)
    └──▶ Agent D ranks [=====' ] Ranking 4  (330ms, blind)
    │
    ▼ ~350ms elapsed
    │
    ▼ Parse rankings & aggregate consensus scores

STAGE 3: CEO Synthesis (~300ms)
    │ [Names revealed, read aggregate rankings]
    │
    ▼ CEO reads: All opinions (named) + all reviews + scores
    │
    [=========] CEO Final Synthesis  (300ms)
    │
    ▼ Total: ~300 + 350 + 300 = ~950ms
Final Output: Superior synthesized answer
```

**Use Case:** High-stakes decisions, peer review  
**Communication:** Parallel→Anonymous→Parallel→Named  
**Total Time:** Sum of stages (can't be parallelized)  
**Key Feature:** Anonymous review prevents bias  

---

## Agent Roles & Perspectives (Council Pattern)

```
┌────────────────────────────────────────────────────────────┐
│ AGENT ROLE SYSTEM PROMPTS                                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Role: CEO                                                  │
│ ────────────────────────────────────────────────────────  │
│ System Prompt: "You are a C-level executive..."           │
│ Focuses on:    Strategic vision, business impact,         │
│                ROI, organizational fit                     │
│                                                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Role: CTO                                                  │
│ ─────────────────────────────────────────────────────────  │
│ System Prompt: "You are a CTO with deep technical..."     │
│ Focuses on:    Architecture, scalability, security,       │
│                technology choices, engineering trade-offs │
│                                                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Role: MANAGER                                              │
│ ────────────────────────────────────────────────────────  │
│ System Prompt: "You are a Project Manager..."             │
│ Focuses on:    Execution, timelines, team capacity,       │
│                milestones, dependencies, practical steps    │
│                                                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Role: EMPLOYEE                                             │
│ ────────────────────────────────────────────────────────  │
│ System Prompt: "You are a specialist engineer..."         │
│ Focuses on:    Implementation details, hands-on insights, │
│                ground-level specifics, technical depth     │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Message Flow Example: Council Task Completion

```
Timeline (in ms):

0ms     User submits task
        POST /api/tasks
        └─▶ Task created, id=123, status=PENDING
        └─▶ Returns immediately with 201

~50ms   Background task starts execution
        └─▶ Task status → RUNNING
        
~100ms  STAGE 1 kicks off
        └─▶ Log: "📋 STAGE 1: Collecting opinions..."
        └─▶ Broadcast to WebSocket subscribers
        
~200ms  Opinions arriving (parallel calls to LLM)
        └─▶ Agent A done: Opinion A stored
        └─▶ Log: "[Agent A] responded in 250ms"
        └─▶ Agent B done: Opinion B stored
        └─▶ Agent C done: Opinion C stored
        └─▶ Agent D done: Opinion D stored
        
~350ms  STAGE 1 complete
        └─▶ Log: "✓ Stage 1 complete — 4 opinions"
        └─▶ Broadcast

~400ms  STAGE 2 kicks off
        └─▶ Opinions anonymized (A, B, C, D)
        └─▶ Log: "🔍 STAGE 2: Anonymous peer review..."
        └─▶ Broadcast
        
~700ms  Reviews & rankings arriving (parallel)
        └─▶ Agent A ranks: Response C, A, D, B
        └─▶ Agent B ranks: Response A, C, B, D
        └─▶ Agent C ranks: Response B, A, C, D
        └─▶ Agent D ranks: Response D, B, A, C
        
~850ms  Rankings aggregated
        └─▶ Log: "Aggregated peer rankings computed"
        └─▶ Consensus: A (avg_rank=1.5), C (2.0), B (2.25), D (3.0)
        
~900ms  STAGE 3 kicks off
        └─▶ Log: "👑 STAGE 3: CEO synthesis..."
        └─▶ CEO reads all opinions (names revealed)
        └─▶ CEO reads all rankings and scores
        
~1200ms CEO synthesis arrives
        └─▶ Final synthesis stored in task.final_output
        └─▶ Task status → COMPLETED
        └─▶ Log: "👑 Council deliberation complete!"
        
~1250ms Frontend polling detects completion
        └─▶ GET /api/tasks/123
        └─▶ Receives final output + all step details
        └─▶ Displays result to user
```

---

## Node Architecture (Simplified)

```
┌───────────────────────────────────────────────────────────────┐
│  WEB CLIENTS                                                  │
│  (Browser, Mobile, Desktop)                                   │
└──────┬──────────────────────────────────────┬─────────────────┘
       │ HTTP REST                             │ WebSocket
       │ (polling-based)                       │ (push-based)
       │                                       │
       ▼                                       ▼
┌──────────────────────────────────────────────────────────────┐
│  FASTAPI SERVER (Port 8000)                                  │
│                                                              │
│  API Routers:                   Services:                    │
│  • /agents          ┐            • orchestrator.py           │
│  • /tasks           ├──────▶      (4 strategies)             │
│  • /ws              ┘             • llm_client.py            │
│                                   (OpenRouter gateway)       │
│                                   • logger.py                │
│                                   (Pub/Sub)                  │
│                                                              │
│  Database:                                                   │
│  ┌────────────────────────────────────────┐                │
│  │ SQLite/PostgreSQL                      │                │
│  │ • agents (30-100 rows)                 │                │
│  │ • tasks  (100-10k rows)                │                │
│  │ • task_steps (500-100k rows)           │                │
│  │ • log_entries (1k-1M rows)             │                │
│  └────────────────────────────────────────┘                │
│                                                              │
│  HTTP Client Pool (Shared):                                  │
│  ┌────────────────────────────────────────┐                │
│  │ httpx.AsyncClient                      │                │
│  │ • max_connections=100                  │                │
│  │ • max_keepalive_connections=20         │                │
│  │ • Timeout=120s per request              │                │
│  └────────────────────────────────────────┘                │
│                                                              │
└──────────────┬───────────────────────────────────────────────┘
               │ HTTP requests to LLM endpoints
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  OpenRouter API Gateway                                      │
│  https://api.openrouter.io/api/v1/chat/completions          │
│                                                              │
│  Provides access to:                                         │
│  • OpenAI (GPT-5, GPT-4)                                     │
│  • Google (Gemini-3)                                         │
│  • Anthropic (Claude-4.5, Claude-3)                          │
│  • X.AI (Grok-4)                                             │
│  • And 50+ other models                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## Concurrency Model

```
Single FastAPI server process
    │
    ├─ Main async loop: uvicorn event loop
    │  (Handles HTTP requests, WebSocket connections)
    │
    └─▶ Background task pool (asyncio.gather)
        │
        ├─ When task created:
        │  │
        │  └─▶ asyncio.create_task(_run_task_background)
        │     (Background task added to event loop)
        │
        ├─ Inside background task:
        │  │
        │  ├─ SEQUENTIAL:  1 agent at a time
        │  │              (await agent1, then await agent2)
        │  │
        │  ├─ PARALLEL:   All agents at once
        │  │              (await asyncio.gather(agent1, agent2, agent3, agent4))
        │  │
        │  ├─ DYNAMIC:    Orchestrator decides
        │  │              (then sequential or parallel)
        │  │
        │  └─ COUNCIL:    3 stages (each has parallel phases)
        │                 Stage 1: 4 agents parallel
        │                 Stage 2: 4 agents parallel (anon review)
        │                 Stage 3: 1 CEO sequential
        │
        └─ Example: Parallel execution
           │
           ▼ asyncio.gather(
             await httpx.post(...)  ──▶ Agent 1 call
             await httpx.post(...)  ──▶ Agent 2 call
             await httpx.post(...)  ──▶ Agent 3 call
             await httpx.post(...)  ──▶ Agent 4 call
           )
           │
           ▼ All 4 calls happen concurrently
             (not sequentially)
```

---

## Error Handling Summary

```
┌─────────────────────────────────┬────────────┬─────────────────┐
│ Error Type                      │ Source     │ Handling        │
├─────────────────────────────────┼────────────┼─────────────────┤
│ Network timeout (120s exceeded) │ httpx      │ Log error,      │
│                                  │            │ skip agent,     │
│                                  │            │ continue        │
├─────────────────────────────────┼────────────┼─────────────────┤
│ LLM returned 500 error          │ OpenRouter │ Log error,      │
│                                  │            │ mark step FAIL  │
├─────────────────────────────────┼────────────┼─────────────────┤
│ JSON parse error (invalid resp)  │ orchestr   │ Log error,      │
│                                  │            │ mark task FAIL  │
├─────────────────────────────────┼────────────┼─────────────────┤
│ Database transaction conflict    │ SQLAlch    │ Rollback,       │
│                                  │            │ attempt recovery│
├─────────────────────────────────┼────────────┼─────────────────┤
│ Server restart mid-task          │ FastAPI   │ Reset in-flight │
│                                  │ lifespan  │ tasks to FAILED │
└─────────────────────────────────┴────────────┴─────────────────┘
```

---

## Key Takeaways

```
1. FRAMEWORK FOR MULTI-AGENT COMMUNICATION:
   └─▶ FastAPI (async) + asyncio.gather (parallelism)
       + SQLAlchemy ORM (persistence) + WebSocket (real-time)

2. HOW AGENTS COMMUNICATE WITH EACH OTHER:
   └─▶ Through the Orchestrator service
       └─▶ Sequential: Pass output as input
       └─▶ Parallel: All query LLM, orchestrator aggregates
       └─▶ Council: Anonymous first, then named synthesis

3. HOW AGENTS COMMUNICATE WITH LLM:
   └─▶ httpx AsyncClient (HTTP requests to OpenRouter API)
       └─▶ Shared connection pool (100 connections max)
       └─▶ Keep-alive for reuse (20 persistent)

4. HOW FRONTEND GETS UPDATES:
   └─▶ Polling (GET /api/tasks/{id})
       └─▶ Real-time (WebSocket /api/ws/logs/{task_id})

5. WHERE STATE LIVES:
   └─▶ Database (SQL): agents, tasks, steps, logs
       └─▶ Memory: Async tasks running in background

6. SCALING CONSIDERATIONS:
   └─▶ Single server (current): OK for <100 concurrent tasks
       └─▶ Multiple servers (future): Need message queue + distributed session
```

---

**Document Generated:** March 10, 2026  
**System:** Lucy Multi-Agent Orchestrator Platform  
**Status:** Complete architecture analysis with ASCII diagrams
