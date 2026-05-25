# Lucy — Multi-Agent Communication: Implementation Flow Diagrams

Detailed ASCII flow diagrams showing exact code paths and data transformations.

> **Status:** The diagrams below trace the original strategy execution flows. They remain accurate for the orchestration core, but the system has evolved:
> - Each agent step now runs an **agentic tool loop** (LLM → parse `<tool_call>` → execute → re-call) instead of a single LLM call
> - All graphs end with a `build_structured_output_node` that assembles a `StructuredOutput` dict
> - Most tasks are now spawned from chat sessions via `POST /api/sessions/{id}/messages` (SSE-streamed) rather than the direct `POST /api/tasks` endpoint
>
> See [LANGGRAPH.md](LANGGRAPH.md) for the agentic loop and structured output node details, and [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for the up-to-date system overview.

---

## Table of Contents

1. [Task Creation to Execution](#1-task-creation-to-execution)
2. [Strategy Execution Flows](#2-strategy-execution-flows)
3. [Council Pattern - Detailed Steps](#3-council-pattern---detailed-steps)
4. [LLM Integration - HTTP Flow](#4-llm-integration---http-flow)
5. [Logging & Broadcasting Flow](#5-logging--broadcasting-flow)
6. [Agent Management Lifecycle](#6-agent-management-lifecycle)

---

## 1. Task Creation to Execution

### Complete Sequence Diagram

```
USER FRONTEND                       FASTAPI ROUTER           ORCHESTRATOR SERVICE           LLM GATEWAY
     │                                  │                          │                            │
     │ POST /api/tasks                  │                          │                            │
     │ {prompt, strategy, agent_ids}    │                          │                            │
     ├─────────────────────────────────▶│                          │                            │
     │                                  │                          │                            │
     │                                  │ (1) Validate TaskCreate  │                            │
     │                                  │ (2) Query agents from DB │                            │
     │                                  │ (3) Create Task record   │                            │
     │                                  │     INSERT tasks TABLE   │                            │
     │                                  │     status = PENDING     │                            │
     │                                  │                          │                            │
     │                                  │ (4) Launch background    │                            │
     │                                  │     task:                │                            │
     │                                  │     _run_task_background │                            │
     │                                  │                          │                            │
     │◀─────► 201 CREATED ◀─────────────│ (5) RETURN immediately   │                            │
     │        {id: 123, ...}            │                          │                            │
     │                                  │                          │                            │
     │ (Frontend starts polling          │                          │                            │
     │  /api/tasks/123 in 500ms)         │                          │                            │
     │                                  │                          │                            │
     │                                  │  (Background process continues asynchronously)       │
     │                                  │                          │                            │
     │                                  │ (6) async with session:  │                            │
     │                                  │     task = await        │                            │
     │                                  │     session.get(123)     │                            │
     │                                  │                          │                            │
     │                                  │                          │ (7) UPDATE task.status    │
     │                                  │                          │     = RUNNING             │
     │                                  │                          │                            │
     │                                  │                          │ (8) IF strategy == council│
     │                                  │                          │     CALL:                 │
     │                                  │                          │     execute_council      │
     │                                  │                          │     (session, task,      │
     │                                  │                          │      agents)              │
     │                                  │                          │                            │
     │                      (Orchestrator runs strategy...) ────────▶│ (See flow below)        │
     │                                  │                          │                            │
     │                                  │                          │ (9) After strategy       │
     │                                  │                          │     completes:           │
     │                                  │                          │     UPDATE task.status   │
     │                                  │                          │     = COMPLETED/FAILED   │
     │                                  │                          │     task.final_output    │
     │                                  │                          │     = <result>           │
     │                                  │                          │                            │
     │                                  │ (10) Commit transaction  │                            │
     │                                  │  session.commit()        │                            │
     │                                  │                          │                            │
     │ GET /api/tasks/123               │                          │                            │
     │ (polling finds completed)        │                          │                            │
     ├─────────────────────────────────▶│                          │                            │
     │                                  │ query.result →           │                            │
     │◀─────── {task with final output} │ return TaskResponse      │                            │
     │                                  │                          │                            │
     ▼                                  ▼                          ▼                            ▼
```

### Code Path in routers/tasks.py

```python
@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db)):
    │
    ├─► Validate: data.strategy in [SEQUENTIAL, PARALLEL, DYNAMIC, COUNCIL]
    │
    ├─► Query agents:
    │   SELECT agents WHERE id IN agent_ids AND is_active AND operational_status=ACTIVE
    │
    ├─► Create Task:
    │   task = Task(
    │     prompt=data.prompt,
    │     strategy=TaskStrategy(data.strategy),
    │     status=TaskStatus.PENDING,
    │     created_at=datetime.now(timezone.utc)
    │   )
    │   db.add(task)
    │   await db.flush()
    │   await db.refresh(task)
    │
    ├─► Launch background:
    │   task_ref = asyncio.create_task(
    │     _run_task_background(task.id, agent_ids)
    │   )
    │   _background_tasks.add(task_ref)
    │   task_ref.add_done_callback(_background_tasks.discard)
    │
    └─► RETURN {task with 201}
```

---

## 2. Strategy Execution Flows

### Sequential Strategy

```
execute_sequential(session, task, agents=[A, B, C])
│
├─ Log: "Starting SEQUENTIAL with 3 agents"
│
├─ accumulated_context = task.prompt
│
├─ Step 1: Agent A
│  │
│  ├─ _run_step(task.id, agent_a, accumulated_context, step_order=0)
│  │  │
│  │  ├─ GET agent_a from cache or DB
│  │  │
│  │  ├─ POST to OpenRouter API:
│  │  │  endpoint = agent_a.endpoint
│  │  │  model = agent_a.model_name
│  │  │  prompt = accumulated_context
│  │  │  max_tokens = ...
│  │  │
│  │  ├─ RESPONSE: response_text (2000+ chars)
│  │  │
│  │  ├─ CREATE TaskStep:
│  │  │  step = TaskStep(
│  │  │    task_id=task.id,
│  │  │    agent_id=agent_a.id,
│  │  │    order=0,
│  │  │    status=COMPLETED,
│  │  │    response=response_text,
│  │  │    duration_ms=245
│  │  │  )
│  │  │  session.add(step)
│  │  │
│  │  ├─ Log broadcast: "[Agent A] responded in 245ms"
│  │  │
│  │  └─ RETURN {"status": COMPLETED, "response": response_text, "duration_ms": 245}
│  │
│  └─ accumulated_context = f"Original: {task.prompt}\n\nPrevious (A): {response_text}\n\nPlease continue..."
│
├─ Step 2: Agent B
│  │
│  ├─ _run_step(task.id, agent_b, accumulated_context, step_order=1)
│  │  [Same flow as Agent A]
│  │
│  └─ accumulated_context = f"Original: ...\n\nPrevious (A): ...\n\nPrevious (B): {new_response}\n\nContinue..."
│
├─ Step 3: Agent C
│  │
│  ├─ _run_step(task.id, agent_c, accumulated_context, step_order=2)
│  │
│  └─ final_response = response_from_agent_c
│
├─ Update Task:
│  │
│  task.status = COMPLETED
│  task.final_output = final_response
│  task.completed_at = now()
│
└─ Log: "Sequential execution completed successfully"
```

### Parallel Strategy

```
execute_parallel(session, task, agents=[A, B, C, D])
│
├─ Log: "Starting PARALLEL with 4 agents"
│
├─ FAN-OUT (asyncio.gather):
│  │
│  │  async def run_agent(agent, order):
│  │      return await _run_step(task.id, agent, task.prompt, step_order=order)
│  │
│  │  steps = await asyncio.gather(
│  │      run_agent(agents[0], 0),  ┐ These 4 HTTP calls
│  │      run_agent(agents[1], 1),  ├ happen in PARALLEL
│  │      run_agent(agents[2], 2),  │ (concurrent, not sequential)
│  │      run_agent(agents[3], 3)   ┘
│  │  )
│  │
│  └─ All 4 agents respond (may take ~300ms max instead of 300*4=1200ms)
│
├─ AGGREGATE:
│  │
│  ├─ Filter successful responses:
│  │  responses = [
│  │      {"agent": "Agent A", "model": "gpt-5", "role": "CEO", "response": "..."},
│  │      {"agent": "Agent B", "model": "gemini-3", "role": "CTO", "response": "..."},
│  │      {"agent": "Agent C", "model": "claude-4.5", "role": "Mgr", "response": "..."},
│  │      {"agent": "Agent D", "model": "grok-4", "role": "Eng", "response": "..."}
│  │  ]
│  │
│  ├─ Log: "Collected 4 responses, aggregating..."
│  │
│  ├─ Query for orchestrator_agent:
│  │  SELECT agents WHERE is_orchestrator=True AND is_active AND operational_status=ACTIVE
│  │
│  └─ IF orchestrator_Agent exists:
│     │
│     ├─ synthesis_prompt = (
│     │  "You are Lucy, orchestrator. Multiple agents answered:\n\n"
│     │  "--- Agent A (gpt-5, CEO) ---\n{response_A}\n\n"
│     │  "--- Agent B (gemini-3, CTO) ---\n{response_B}\n\n"
│     │  "...\n\n"
│     │  "Synthesize into one definitive answer."
│     │  )
│     │
│     ├─ synth_step = _run_step(
│     │      task.id,
│     │      orchestrator_agent,
│     │      synthesis_prompt,
│     │      step_order=4  # After the 4 parallel steps
│     │  )
│     │
│     ├─ IF synth_step.status == COMPLETED:
│     │  task.final_output = synth_step.response
│     │
│     └─ ELSE:
│        task.final_output = "\n\n---\n\n".join all responses
│
└─ Update Task:
   task.status = COMPLETED
   task.completed_at = now()
   Log: "Parallel execution completed"
```

### Dynamic Strategy

```
execute_dynamic(session, task, agents=[A, B, C, D])
│
├─ Log: "Starting DYNAMIC — consulting orchestrator..."
│
├─ Query orchestrator_agent
│
├─ Build agent_catalog:
│  │
│  agent_catalog = [
│      {
│        "id": 1,
│        "name": "Agent A",
│        "model": "gpt-5",
│        "role": "CEO",
│        "description": "..."
│      },
│      {
│        "id": 2,
│        "name": "Agent B",
│        "model": "gemini-3",
│        "role": "CTO",
│        "description": "..."
│      },
│      ...
│  ]
│
├─ routing_prompt = (
│  "You are Lucy. Route this query:\n"
│  "QUERY: {task.prompt}\n\n"
│  "AVAILABLE AGENTS: {json.dumps(agent_catalog)}\n\n"
│  "Respond with: {\"strategy\": \"sequential|parallel\", "agent_ids\": [...], \"reasoning\": \"...\"}"
│  )
│
├─ routing_step = _run_step(task.id, orchestrator_agent, routing_prompt, step_order=0)
│
├─ decision = json.loads(routing_step.response)
│  │
│  ├─ sub_strategy = decision["strategy"]           # "sequential" or "parallel"
│  ├─ selected_ids = decision["agent_ids"]          # [1, 3, 2] (reordered)
│  └─ reasoning = decision["reasoning"]
│
├─ Query for selected agents from DB
│
├─ Log: f"Routing decision: {sub_strategy} with agents {selected_ids}. Reason: {reasoning}"
│
├─ IF sub_strategy == "sequential":
│  │
│  └─ Call execute_sequential(session, task, selected_agents)
│
└─ ELSE (parallel):
   │
   └─ Call execute_parallel(session, task, selected_agents)
```

---

## 3. Council Pattern - Detailed Steps

### STAGE 1: Collect Independent Opinions

```
execute_council(session, task, agents=[CEO, CTO, Mgr, Eng])
│
├─ [1] Find CEO Agent
│  │
│  ├─ ceo_agent = next(a for a in agents if a.is_orchestrator)
│  │
│  └─ IF NOT ceo_agent:
│     ceo_agent = next(a for a in agents if a.role == "ceo")
│
├─ Log: "📋 STAGE 1: Collecting individual opinions from all agents..."
│
├─ step_counter = 0
│
├─ Define async function get_opinion(agent, order):
│  │
│  ├─ role_prompt = ROLE_SYSTEM_PROMPTS[agent.role.value]
│  │  ("You are a C-level executive...", "You are a CTO...", etc.)
│  │
│  ├─ prompt = f"{role_prompt}\n\nYou are {agent.name} (Role: {agent.role.upper()}).\n\nAnalyze:\n\n{task.prompt}"
│  │
│  └─ RETURN await _run_step(task.id, agent, prompt, step_order=order, step_label="opinion")
│
├─ Launch PARALLEL (asyncio.gather):
│  │
│  opinion_steps = await asyncio.gather(
│      get_opinion(agents[0], 0),  ┐
│      get_opinion(agents[1], 1),  ├ All 4 in parallel
│      get_opinion(agents[2], 2),  │
│      get_opinion(agents[3], 3)   ┘
│  )
│
├─ step_counter = 4  (4 steps completed)
│
├─ Collect successful opinions:
│  │
│  opinions = []
│  FOR i, result IN opinion_steps:
│      IF result.status == COMPLETED:
│          opinions.append({
│              "agent": agents[i],
│              "response": result.response
│          })
│
├─ IF len(opinions) == 0:
│  │
│  └─ task.status = FAILED, final_output = "No opinions", RETURN
│
└─ Log: f"✓ Stage 1 complete — {len(opinions)} opinions collected"


┌─ STAGE 1 OUTPUT (Example) ─────────────────────┐
│                                                 │
│ opinions = [                                    │
│   {                                             │
│     "agent": Agent(id=1, name="CEO Agent",     │
│                    role="CEO", ...),            │
│     "response": "As a C-level executive...[...] │
│   },                                            │
│   {                                             │
│     "agent": Agent(id=2, name="CTO Agent",     │
│                    role="CTO", ...),            │
│     "response": "From a technical perspective..│
│   },                                            │
│   ...                                           │
│ ]                                               │
│                                                 │
└─────────────────────────────────────────────────┘
```

### STAGE 2: Anonymous Blind Peer Review

```
Log: "🔍 STAGE 2: Anonymous peer review..."

├─ [2a] Create Anonymous Labels
│  │
│  ├─ labels = ["Response A", "Response B", "Response C", "Response D"]
│  │
│  ├─ label_to_agent = {
│  │      "Response A": opinions[0]["agent"],
│  │      "Response B": opinions[1]["agent"],
│  │      "Response C": opinions[2]["agent"],
│  │      "Response D": opinions[3]["agent"]
│  │  }
│  │
│  └─ anon_block = (
│     "--- Response A ---\n{opinions[0].response}\n\n"
│     "--- Response B ---\n{opinions[1].response}\n\n"
│     "--- Response C ---\n{opinions[2].response}\n\n"
│     "--- Response D ---\n{opinions[3].response}\n"
│     )
│
├─ [2b] Define async function review_anonymous(reviewing_agent, order):
│  │
│  ├─ role_prompt = ROLE_SYSTEM_PROMPTS[reviewing_agent.role]
│  │
│  ├─ prompt = (
│  │  f"{role_prompt}\n\n"
│  │  f"ORIGINAL QUESTION:\n{task.prompt}\n\n"
│  │  f"RESPONSES (anonymized):\n\n{anon_block}\n\n"
│  │  f"EVALUATE each response.\n"
│  │  f"END YOUR RESPONSE WITH:\n\n"
│  │  f"FINAL RANKING:\n"
│  │  f"1. Response [A/B/C/D]\n"
│  │  f"2. Response [A/B/C/D]\n"
│  │  f"3. Response [A/B/C/D]\n"
│  │  f"4. Response [A/B/C/D]\n"
│  │  )
│  │
│  └─ RETURN await _run_step(task.id, reviewing_agent, prompt, step_order=order, step_label="review")
│
├─ [2c] Launch PARALLEL review by all 4 agents:
│  │
│  reviewing_agents = [op["agent"] for op in opinions]
│
│  review_steps = await asyncio.gather(
│      review_anonymous(reviewing_agents[0], step_counter + 0),  ┐
│      review_anonymous(reviewing_agents[1], step_counter + 1),  ├ All 4 review
│      review_anonymous(reviewing_agents[2], step_counter + 2),  │ in parallel
│      review_anonymous(reviewing_agents[3], step_counter + 3)   ┘
│  )
│
│  step_counter += 4  (now 8 steps total)
│
├─ [2d] Parse Rankings from Review Responses
│  │
│  reviews = []
│  FOR i, result IN review_steps:
│      IF result.status == COMPLETED:
│          reviews.append({
│              "agent": reviewing_agents[i],
│              "response": result.response
│          })
│          
│          # PARSE the "FINAL RANKING:" section
│          parsed_ranking = parse_ranking_from_text(
│              result.response,
│              valid_labels=["Response A", "Response B", "Response C", "Response D"]
│          )
│          # Example: ["Response C", "Response A", "Response D", "Response B"]
│
├─ [2e] Calculate Aggregate Rankings
│  │
│  aggregate = calculate_aggregate_rankings(reviews, label_to_agent)
│  │
│  │ For each agent:
│  │   • Collect all position votes (position 1 = best, 4 = worst)
│  │   • Average the positions
│  │   • Lower average = higher rank
│  │
│  │ Example output:
│  │ [
│  │   {"agent_id": 1, "agent_name": "CEO Agent", "avg_rank": 1.5},
│  │   {"agent_id": 3, "agent_name": "Manager Agent", "avg_rank": 2.0},
│  │   {"agent_id": 2, "agent_name": "CTO Agent", "avg_rank": 2.5},
│  │   {"agent_id": 4, "agent_name": "Engineer Agent", "avg_rank": 3.0}
│  │ ]
│
└─ Log: "Aggregated peer rankings computed"


┌─ STAGE 2 OUTPUT (Example) ────────────────────┐
│                                                 │
│ reviews = [                                     │
│   {                                             │
│     "agent": Agent(id=1, name="CEO Agent"),    │
│     "response": "Response A has...              │
│                 FINAL RANKING:\n1. Response C\ │
│                 2. Response A\n3. Response D\n │
│                 4. Response B"                  │
│   },                                            │
│   ...                                           │
│ ]                                               │
│                                                 │
│ aggregate = [                                   │
│   {"agent_id": 1, "agent_name": "CEO",        │
│    "avg_rank": 1.5},    (most agreed-upon)    │
│   {"agent_id": 3, "agent_name": "Manager",    │
│    "avg_rank": 2.0},                           │
│   {"agent_id": 2, "agent_name": "CTO",        │
│    "avg_rank": 2.5},                           │
│   {"agent_id": 4, "agent_name": "Engineer",   │
│    "avg_rank": 3.0}    (least agreed-upon)    │
│ ]                                               │
│                                                 │
└─────────────────────────────────────────────────┘
```

### STAGE 3: CEO Synthesis

```
Log: "👑 STAGE 3: Chairman synthesizes final answer..."

├─ [3a] Build comprehensive synthesis prompt:
│  │
│  ├─ Include:
│  │  • Original user question
│  │  • All opinions (NOW WITH AUTHOR NAMES + ROLES REVEALED)
│  │  • All peer reviews (with agent names)
│  │  • Aggregate ranking scores
│  │
│  └─ synthesis_prompt = (
│     f"You are the Chairman/CEO reading a complete council deliberation.\n\n"
│     f"ORIGINAL QUESTION:\n{task.prompt}\n\n"
│     f"INDEPENDENT OPINIONS:\n"
│     f"--- {opinions[0].agent.name} ({opinions[0].agent.role}) ---\n{opinions[0].response}\n\n"
│     f"--- {opinions[1].agent.name} ({opinions[1].agent.role}) ---\n{opinions[1].response}\n\n"
│     f"--- {opinions[2].agent.name} ({opinions[2].agent.role}) ---\n{opinions[2].response}\n\n"
│     f"--- {opinions[3].agent.name} ({opinions[3].agent.role}) ---\n{opinions[3].response}\n\n"
│     f"PEER RANKINGS (consensus):\n"
│     f"{json.dumps(aggregate, indent=2)}\n\n"
│     f"ALL PEER REVIEWS:\n"
│     f"(... detailed reviews ...)\n\n"
│     f"SYNTHESIZE a final answer that:\n"
│     f"1. Incorporates consensus points\n"
│     f"2. Notes divergent perspectives with reasoning\n"
│     f"3. Uses ranked evidence (top-ranked items highlighted)\n"
│     f"4. Produces a superior, comprehensive answer"
│     )
│
├─ [3b] Call CEO agent to synthesize:
│  │
│  synth_step = await _run_step(
│      task.id,
│      ceo_agent,
│      synthesis_prompt,
│      step_order=step_counter,  # (8 in this example)
│      step_label="synthesis"
│  )
│
├─ [3c] Process result:
│  │
│  ├─ final_synthesis = synth_step.response
│  │
│  ├─ task.status = COMPLETED
│  │
│  ├─ task.final_output = final_synthesis
│  │
│  └─ task.completed_at = now()
│
└─ Log: "👑 Council deliberation complete!"
```

### Council Pattern Summary Graphic

```
                    USER QUESTION
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
    ┌────────┐       ┌────────┐       ┌────────┐
    │Agent A │       │Agent B │       │Agent C │  (Parallel execution)
    │(CEO)   │       │(CTO)   │       │(Mgr)   │
    └────┬───┘       └────┬───┘       └────┬───┘
         │                │                │
         ▼ Opinion A       ▼ Opinion B      ▼ Opinion C
         │                │                │
         │                ▼                │
         │          ┌─────────────────┐    │
         │          │ Anonymize: A,B,C│    │
         └─────────▶│ (hide authors)  │◀───┘
                    └────┬────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐       ┌────────┐       ┌────────┐
    │Review& │       │Review& │       │Review& │  (All 4 agents evaluate
    │Rank A  │       │Rank B  │       │Rank C  │   anonymized opinions)
    │(CEO)   │       │(CTO)   │       │(Mgr)   │
    └────┬───┘       └────┬───┘       └────┬───┘
         │                │                │
         └────────────────┼────────────────┘
                          │
                          ▼
                 ┌──────────────────────┐
                 │ Aggregate Rankings:  │
                 │ A (score 1.5)        │
                 │ B (score 2.0)        │
                 │ C (score 2.5)        │
                 └──────────┬───────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │ Names revealed + │ Rankings shown + │ Reviews included
         │                  │                  │
         ▼                  ▼                  ▼
    ┌─────────────────────────────────────────────┐
    │ CEO Reads: All opinions (named),            │
    │ All rankings, All reviews                   │
    │ → Synthesizes comprehensive final answer    │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
           ┌──────────────────────┐
           │  FINAL SYNTHESIS     │
           │  (Superior answer)   │
           └──────────────────────┘
```

---

## 4. LLM Integration - HTTP Flow

### HTTP Request to OpenRouter

```
llm_client.chat_completion(
    endpoint="https://api.openrouter.io/api/v1",
    model="openai/gpt-5",
    prompt="Analyze this...",
    max_tokens=2000,
    temperature=0.7
)
│
├─ Construct payload:
│  │
│  payload = {
│      "model": "openai/gpt-5",
│      "messages": [
│          {
│              "role": "user",
│              "content": prompt
│          }
│      ],
│      "max_tokens": 2000,
│      "temperature": 0.7,
│      "top_p": 0.9
│  }
│
├─ Get or create shared httpx.AsyncClient:
│  │
│  client = app.state._http_client  (initialized in FastAPI lifespan)
│  │
│  └─ Features:
│     • Connection pooling (max_connections=100)
│     • Keep-alive (max_keepalive_connections=20)
│     • Timeout: 120s (configurable)
│     • Limits prevent connection exhaustion
│
├─ Make async POST request:
│  │
│  response = await client.post(
│      f"{endpoint}/chat/completions",
│      json=payload,
│      headers={
│          "Authorization": f"Bearer {OPENROUTER_API_KEY}",
│          "HTTP-Referer": "https://lucy-app.com",  # OpenRouter requirement
│          "X-Title": "Lucy Multi-Agent"
│      },
│      timeout=120
│  )
│
├─ Parse response:
│  │
│  data = response.json()
│  │
│  IF "choices" in data:
│      message = data["choices"][0]["message"]["content"]
│      tokens_used = data.get("usage", {}).get("total_tokens", 0)
│      
│      RETURN {
│          "text": message,
│          "tokens": tokens_used,
│          "model": "openai/gpt-5"
│      }
│
├─ Error handling:
│  │
│  EXCEPT httpx.TimeoutException:
│      RAISE "LLM request timed out after 120s"
│
│  EXCEPT httpx.HTTPStatusError:
│      RAISE f"OpenRouter returned {response.status_code}: {response.text}"
│
│  EXCEPT Exception as e:
│      RAISE f"Unexpected error calling OpenRouter: {e}"
│
└─ Return message text to caller (_run_step)


┌─ Example: curl equivalent ────────────────────┐
│                                                 │
│ curl https://api.openrouter.io/api/v1/        │
│   /chat/completions \                          │
│   -H "Authorization: Bearer $OPENROUTER_KEY"\ │
│   -H "HTTP-Referer: https://lucy-app.com" \   │
│   -d '{                                        │
│     "model": "openai/gpt-5",                   │
│     "messages": [{                             │
│       "role": "user",                          │
│       "content": "Analyze: ..."                │
│     }],                                        │
│     "max_tokens": 2000                         │
│   }'                                            │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Health Check Flow

```
llm_client.check_health(endpoint="http://192.168.73.41:9002")
│
├─ POST {endpoint}/v1/chat/completions
│   with minimal payload (10 tokens)
│   timeout = 10s (shorter than normal)
│
├─ Measure latency:
│  │
│  start_time = time.time()
│  response = await client.post(...)
│  latency_ms = (time.time() - start_time) * 1000
│
├─ Return:
│  │
│  IF response.status_code == 200:
│      RETURN (True, latency_ms, response.headers)  # Online
│  ELSE:
│      RETURN (False, latency_ms, error_details)    # Offline
│
└─ Usage (in agents.py):
   │
   is_online, latency, _ = await check_health(endpoint)
   │
   IF is_online:
       agent.infrastructure_status = ONLINE
       agent.is_warm = True
   ELSE:
       agent.infrastructure_status = OFFLINE
```

---

## 5. Logging & Broadcasting Flow

### Log Creation & Broadcast

```
_log(task_id=123, message="Stage 1 complete", level="info", source="orchestrator")
│
├─ [1] Create LogEntry in NEW isolated session:
│  │
│  │ (Important: never use the calling task session)
│  │ (Prevents long-running transaction issues)
│  │
│  async with async_session() as log_session:
│      │
│      entry = LogEntry(
│          task_id=123,
│          level=LogLevel("info"),
│          source="orchestrator",
│          message="Stage 1 complete",
│          timestamp=datetime.now(timezone.utc)
│      )
│      log_session.add(entry)
│      await log_session.commit()
│     
│ Now in database:
│ INSERT INTO log_entries
│   (task_id, level, message, source, timestamp)
│ VALUES
│   (123, 'info', 'Stage 1 complete', 'orchestrator', '2026-03-10T14:32:15Z')
│
├─ [2] Broadcast to all subscribers:
│  │
│  await log_broadcaster.broadcast(
│      message="Stage 1 complete",
│      level="info",
│      source="orchestrator",
│      task_id=123
│  )
│
├─ [3] Inside LogBroadcaster.broadcast():
│  │
│  ├─ Convert to JSON:
│  │  │
│  │  payload = {
│  │      "message": "Stage 1 complete",
│  │      "level": "info",
│  │      "source": "orchestrator",
│  │      "task_id": 123,
│  │      "timestamp": "2026-03-10T14:32:15Z"
│  │  }
│  │  json_str = json.dumps(payload)
│  │
│  └─ Put message on all relevant queues:
│     │
│     IF 'global' in _subscriptions:
│         FOR queue IN _subscriptions['global']:
│             queue.put_nowait(json_str)
│
│     IF 'task:123' in _subscriptions:
│         FOR queue IN _subscriptions['task:123']:
│             queue.put_nowait(json_str)
│
│
│ Now WebSocket handlers are unblocked:
│
│   Handler A (global listener):
│     msg = await queue.get()  → receives json_str
│     await websocket.send_text(json_str)
│
│   Handler B (task:123 listener):
│     msg = await queue.get()  → receives json_str
│     await websocket.send_text(json_str)
│
│   Handler C (task:456 listener):
│     [No message for this task, stays blocked on queue.get()]
│
└─ Completed log flow


┌─ Full Publisher-Subscriber Model ─────────────────────────┐
│                                                             │
│ Orchestrator (Publisher):                                  │
│   await _log(task_id=123, msg="...")                       │
│   → database INSERT                                        │
│   → broadcast to queue                                     │
│                                                             │
│                          │                                 │
│         ┌────────────────┼────────────────┐               │
│         │                │                │               │
│ Subscriber A:      Subscriber B:      Subscriber C:       │
│ Global logs        Task 123 logs      Task 456 logs       │
│                                                             │
│ while True:        while True:        while True:         │
│   msg = await       msg = await        msg = await         │
│   global_queue      task123_queue      task456_queue       │
│   .get()            .get()             .get()              │
│   → ws.send()       → ws.send()        → ws.send()         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Agent Management Lifecycle

### Agent Creation & State Transitions

```
POST /api/agents
{
    "name": "CEO Agent",
    "endpoint": "https://api.openrouter.io/api/v1",
    "role": "ceo",
    "description": "Strategic decision maker",
    "is_orchestrator": true
}
│
├─ [1] Validate input (AgentCreate schema)
│
├─ [2] If model_name not provided:
│  │
│  │ is_orchestrator_model = True
│  │ model_name = "openai/gpt-5.1"  (hardcoded for orchestrator)
│  │
│  └─ TRY: info = await fetch_model_info(endpoint)
│     CATCH: leave model_name as None
│
├─ [3] Probe endpoint for health:
│  │
│  │ is_online, latency, headers = await check_health(endpoint)
│  │
│  └─ IF is_online:
│         infrastructure_status = ONLINE
│         is_warm = True
│     ELSE:
│         infrastructure_status = OFFLINE
│         is_warm = False
│
├─ [4] Create Agent record:
│  │
│  agent = Agent(
│      name="CEO Agent",
│      endpoint="https://api.openrouter.io/api/v1",
│      model_name="openai/gpt-5.1",
│      role=AgentRole.CEO,
│      description="Strategic decision maker",
│      is_orchestrator=True,
│      operational_status=OperationalStatus.ACTIVE,
│      infrastructure_status=InfrastructureStatus.ONLINE,
│      state=AgentState.IDLE,
│      is_active=True,
│      is_warm=True,
│      crash_count=0
│  )
│  db.add(agent)
│  await db.flush()
│  await db.refresh(agent)
│
└─ RETURN AgentResponse with id=1


Agent Lifecycle States:
┌─────────────────────────────────────────────────────────────┐
│  CREATION (IDLE)                                             │
│  ├─ Created in DB                                            │
│  ├─ Probed for health                                        │
│  └─ Ready for tasks                                          │
│                                                              │
│  ▼                                                            │
│  TASK ASSIGNMENT (ASSIGNED)                                  │
│  ├─ Selected for a task step                                │
│  ├─ step = TaskStep(agent_id=agent.id, status=RUNNING)     │
│  ├─ agent.state = ASSIGNED                                  │
│  └─ Ready to execute                                         │
│                                                              │
│  ▼                                                            │
│  EXECUTION (EXECUTING)                                       │
│  ├─ HTTP POST to LLM endpoint                                │
│  ├─ agent.state = EXECUTING                                 │
│  ├─ Waiting for response...                                  │
│  └─ Timeout: 120s                                            │
│                                                              │
│  ▼                                                            │
│  SUCCESS (COMPLETED)                                         │
│  ├─ Response received                                        │
│  ├─ step.status = COMPLETED                                 │
│  ├─ step.response = <text>                                   │
│  ├─ agent.state = IDLE                                       │
│  ├─ Update avg_response_time_ms (exponential moving average) │
│  ├─ agent.is_warm = True (can respond immediately)           │
│  └─ Ready for next task                                      │
│                                                              │
│  OR                                                           │
│                                                              │
│  FAILURE (FAILED)                                            │
│  ├─ Network error / timeout / parse error                    │
│  ├─ step.status = FAILED                                     │
│  ├─ step.response = "ERROR: ..."                             │
│  ├─ agent.state = FAILED                                     │
│  ├─ agent.crash_count += 1                                   │
│  ├─ agent.infrastructure_status = OFFLINE                    │
│  └─ Excluded from future tasks (is_active filter)            │
│                                                              │
│  Manual operations:                                          │
│  ├─ PUT /api/agents/{id} → Update role, reactivate          │
│  ├─ DELETE /api/agents/{id} → Mark is_active = False        │
│  └─ Health check re-probe                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Metrics Tracked

```
PER AGENT:
  • operational_status: ACTIVE | INACTIVE | PAUSED | STOPPED | FAILED
  • infrastructure_status: ONLINE | OFFLINE
  • state: IDLE | ASSIGNED | EXECUTING | COMPLETED | FAILED
  • avg_response_time_ms: Float (exponential moving average)
  • crash_count: Integer (incremented on errors)
  • is_warm: Boolean (True after successful response)

PER TASK:
  • status: PENDING | RUNNING | COMPLETED | FAILED
  • strategy: SEQUENTIAL | PARALLEL | DYNAMIC | COUNCIL
  • steps_count: Integer (depends on strategy & parallelism)
  • completion_time: Total time from creation to completion

PER STEP:
  • status: PENDING | RUNNING | COMPLETED | FAILED
  • duration_ms: Response time for this agent
  • step_label: "opinion" | "review" | "synthesis"

PER LOG:
  • level: INFO | WARNING | ERROR | DEBUG | AGENT
  • source: Agent name or "orchestrator"
  • timestamp: When log was created
```

---

**End of Implementation Flow Diagrams**
