# LLM Council — Detailed Multi-Agent Communication Architecture

> A deep-dive into how multiple AI agents deliberate, communicate, rank each other, and produce a final synthesized answer.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [Agents & Roles](#3-agents--roles)
4. [Communication Infrastructure](#4-communication-infrastructure)
5. [The 3-Stage Deliberation Process](#5-the-3-stage-deliberation-process)
   - [Stage 1 — Independent Responses](#stage-1--independent-responses)
   - [Stage 2 — Anonymous Peer Review](#stage-2--anonymous-peer-review)
   - [Stage 3 — Chairman Synthesis](#stage-3--chairman-synthesis)
6. [Data Structures & Payloads](#6-data-structures--payloads)
7. [API Layer](#7-api-layer)
8. [Streaming Protocol (SSE)](#8-streaming-protocol-sse)
9. [Anonymization & De-anonymization](#9-anonymization--de-anonymization)
10. [Ranking Parsing Algorithm](#10-ranking-parsing-algorithm)
11. [Aggregate Ranking Calculation](#11-aggregate-ranking-calculation)
12. [Storage & Persistence](#12-storage--persistence)
13. [Frontend State Machine](#13-frontend-state-machine)
14. [Error Handling & Graceful Degradation](#14-error-handling--graceful-degradation)
15. [Complete Data Flow Diagram](#15-complete-data-flow-diagram)
16. [Key Design Decisions](#16-key-design-decisions)

---

## 1. System Overview

LLM Council is a **multi-agent deliberation system** where several independent AI models:
1. Each answer a user's question independently (no awareness of each other)
2. Evaluate and rank each other's answers **without knowing who wrote what** (blind peer review)
3. A designated "Chairman" model reads all responses and all rankings, then synthesizes a final, superior answer

This mirrors how human expert panels or academic peer review works — independent perspectives, anonymous critique, then synthesis.

```
┌─────────────────────────────────────────────────────────┐
│                      USER QUERY                         │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────▼───────────────┐
          │         STAGE 1               │
          │   All 4 models answer in      │
          │   parallel, independently     │
          └───────────────┬───────────────┘
                          │
          ┌───────────────▼───────────────┐
          │         STAGE 2               │
          │   Responses are anonymized    │
          │   All 4 models rank each      │
          │   other's work (blind)        │
          └───────────────┬───────────────┘
                          │
          ┌───────────────▼───────────────┐
          │         STAGE 3               │
          │   Chairman reads everything   │
          │   Synthesizes final answer    │
          └───────────────┬───────────────┘
                          │
          ┌───────────────▼───────────────┐
          │       FINAL RESPONSE          │
          │   Returned to user with       │
          │   full transparency           │
          └───────────────────────────────┘
```

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python + FastAPI | Async API server |
| **LLM Gateway** | OpenRouter API | Unified endpoint for all models |
| **HTTP Client** | `httpx` (async) | Non-blocking model requests |
| **Concurrency** | `asyncio.gather()` | Parallel model queries |
| **Streaming** | Server-Sent Events (SSE) | Progressive stage delivery |
| **Storage** | JSON files on disk | Conversation persistence |
| **Frontend** | React (Vite) | UI for conversation & stage inspection |
| **Markdown** | `react-markdown` | Renders model outputs |

---

## 3. Agents & Roles

### Council Members (defined in `backend/config.py`)

These 4 models participate in both Stage 1 (answering) and Stage 2 (ranking):

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]
```

### Chairman (defined in `backend/config.py`)

This single model participates only in Stage 3 (synthesis). It reads all outputs and rankings:

```python
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

> **Note:** The Chairman can be the same model as one of the council members. It receives **named** (non-anonymous) context, unlike in Stage 2.

### Model Identifiers

All model identifiers follow OpenRouter's format: `provider/model-name`. This allows switching any model without changing the communication logic — just update `config.py`.

---

## 4. Communication Infrastructure

### OpenRouter as the Unified Gateway

All agents communicate through a single API endpoint:

```
POST https://openrouter.ai/api/v1/chat/completions
```

This means the backend never talks directly to OpenAI, Google, Anthropic, or xAI. Instead, OpenRouter acts as a **universal proxy**, translating the request format for each provider.

### `query_model()` — Single Agent Request

```python
# backend/openrouter.py

async def query_model(model: str, messages: list, timeout: float = 120.0):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,       # e.g. "openai/gpt-5.1"
        "messages": messages, # OpenAI-style chat format
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
        data = response.json()
        message = data['choices'][0]['message']
        return {
            'content': message.get('content'),
            'reasoning_details': message.get('reasoning_details')  # for reasoning models
        }
```

**Request format** (standard OpenAI chat format):
```json
{
  "model": "openai/gpt-5.1",
  "messages": [
    { "role": "user", "content": "What is quantum entanglement?" }
  ]
}
```

**Response extraction:**
```json
{
  "choices": [{
    "message": {
      "content": "Quantum entanglement is...",
      "reasoning_details": null
    }
  }]
}
```

### `query_models_parallel()` — All Agents at Once

```python
# backend/openrouter.py

async def query_models_parallel(models: list, messages: list):
    tasks = [query_model(model, messages) for model in models]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
```

`asyncio.gather()` launches **all model requests simultaneously**. They all run concurrently — the total wait time is the slowest single model, not the sum of all models.

**Example timing (4 models):**
```
Without parallel:  2s + 3s + 4s + 2s = 11s total
With asyncio:      max(2s, 3s, 4s, 2s) = 4s total
```

---

## 5. The 3-Stage Deliberation Process

All three stages are orchestrated in `backend/council.py`.

---

### Stage 1 — Independent Responses

**File:** `backend/council.py → stage1_collect_responses()`

**Goal:** Get each council model's best, unbiased answer to the user's question.

**What happens:**
1. User query is wrapped in a standard OpenAI-format `messages` list
2. All 4 council models are queried in **parallel**
3. Results are collected; failed responses (`None`) are silently dropped

```python
async def stage1_collect_responses(user_query: str):
    messages = [{"role": "user", "content": user_query}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    stage1_results = []
    for model, response in responses.items():
        if response is not None:
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })
    return stage1_results
```

**Prompt sent to each model:**
```
[Just the raw user query — no framing, no instructions]
```

**Output shape:**
```json
[
  { "model": "openai/gpt-5.1", "response": "..." },
  { "model": "google/gemini-3-pro-preview", "response": "..." },
  { "model": "anthropic/claude-sonnet-4.5", "response": "..." },
  { "model": "x-ai/grok-4", "response": "..." }
]
```

**Key property:** Each model answers in complete **isolation**. They have no knowledge of each other's responses at this point.

---

### Stage 2 — Anonymous Peer Review

**File:** `backend/council.py → stage2_collect_rankings()`

**Goal:** Have each model critically evaluate and rank all responses — without knowing who wrote what (to prevent favoritism or bias toward self or familiar models).

#### Step 1: Anonymization

Responses are stripped of model identity and assigned letter labels:

```python
labels = [chr(65 + i) for i in range(len(stage1_results))]
# → ['A', 'B', 'C', 'D']

label_to_model = {
    f"Response {label}": result['model']
    for label, result in zip(labels, stage1_results)
}
# → {"Response A": "openai/gpt-5.1", "Response B": "google/gemini-3-pro-preview", ...}
```

The `label_to_model` mapping is the **secret decoder ring** — it maps anonymous labels back to real model names, but models never see it.

#### Step 2: Ranking Prompt Construction

All 4 anonymized responses are bundled into a single prompt:

```
You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

Response A:
{response_from_model_1}

Response B:
{response_from_model_2}

Response C:
{response_from_model_3}

Response D:
{response_from_model_4}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example:
...evaluation text...

FINAL RANKING:
1. Response C
2. Response A
3. Response B
4. Response D
```

#### Step 3: Parallel Ranking Queries

The **exact same prompt** is sent to **all 4 council models simultaneously**:

```python
messages = [{"role": "user", "content": ranking_prompt}]
responses = await query_models_parallel(COUNCIL_MODELS, messages)
```

Each model now acts as both a **participant** (it wrote one of the anonymous responses) and a **judge** (it ranks all 4 responses, including its own, without knowing which is its own).

#### Step 4: Parsing Rankings

Each model's response is parsed to extract the structured ranking:

```python
for model, response in responses.items():
    if response is not None:
        full_text = response.get('content', '')
        parsed = parse_ranking_from_text(full_text)
        stage2_results.append({
            "model": model,
            "ranking": full_text,      # full evaluation text
            "parsed_ranking": parsed   # ["Response C", "Response A", ...]
        })
```

**Output shape:**
```json
[
  {
    "model": "openai/gpt-5.1",
    "ranking": "Response A provides good detail on X but misses Y...\n\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response D\n4. Response B",
    "parsed_ranking": ["Response C", "Response A", "Response D", "Response B"]
  },
  ...
]
```

**Return value:**
```python
return stage2_results, label_to_model
```

Both the rankings AND the decoder mapping are returned together.

---

### Stage 3 — Chairman Synthesis

**File:** `backend/council.py → stage3_synthesize_final()`

**Goal:** One authoritative model reads everything — all responses AND all peer rankings — and synthesizes the single best final answer.

#### Context Given to Chairman

The chairman receives **full context with real model names** (not anonymous):

```
You are the Chairman of an LLM Council. Multiple AI models have provided 
responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
Model: openai/gpt-5.1
Response: {full response text}

Model: google/gemini-3-pro-preview
Response: {full response text}

... (all 4 models)

STAGE 2 - Peer Rankings:
Model: openai/gpt-5.1
Ranking: {full evaluation + FINAL RANKING section}

Model: google/gemini-3-pro-preview
Ranking: {full evaluation + FINAL RANKING section}

... (all 4 evaluations)

Your task as Chairman is to synthesize all of this information into a single, 
comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's 
collective wisdom:
```

#### Chairman Query

Unlike Stages 1 and 2, the chairman is a **single query** (not parallel):

```python
response = await query_model(CHAIRMAN_MODEL, messages)
```

**Output shape:**
```json
{
  "model": "google/gemini-3-pro-preview",
  "response": "Based on the council's deliberation, the most accurate and comprehensive answer is..."
}
```

---

## 6. Data Structures & Payloads

### Full Council Run Output

The top-level `run_full_council()` function returns a 4-tuple:

```python
async def run_full_council(user_query: str):
    stage1_results = await stage1_collect_responses(user_query)
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    stage3_result = await stage3_synthesize_final(user_query, stage1_results, stage2_results)

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata
```

### Complete Response Payload (from API)

```json
{
  "stage1": [
    { "model": "openai/gpt-5.1", "response": "..." },
    { "model": "google/gemini-3-pro-preview", "response": "..." },
    { "model": "anthropic/claude-sonnet-4.5", "response": "..." },
    { "model": "x-ai/grok-4", "response": "..." }
  ],
  "stage2": [
    {
      "model": "openai/gpt-5.1",
      "ranking": "Response A provides... FINAL RANKING:\n1. Response C...",
      "parsed_ranking": ["Response C", "Response A", "Response D", "Response B"]
    },
    { "model": "google/gemini-3-pro-preview", "ranking": "...", "parsed_ranking": [...] },
    { "model": "anthropic/claude-sonnet-4.5", "ranking": "...", "parsed_ranking": [...] },
    { "model": "x-ai/grok-4", "ranking": "...", "parsed_ranking": [...] }
  ],
  "stage3": {
    "model": "google/gemini-3-pro-preview",
    "response": "Based on the council's deliberation..."
  },
  "metadata": {
    "label_to_model": {
      "Response A": "openai/gpt-5.1",
      "Response B": "google/gemini-3-pro-preview",
      "Response C": "anthropic/claude-sonnet-4.5",
      "Response D": "x-ai/grok-4"
    },
    "aggregate_rankings": [
      { "model": "anthropic/claude-sonnet-4.5", "average_rank": 1.5, "rankings_count": 4 },
      { "model": "openai/gpt-5.1", "average_rank": 2.25, "rankings_count": 4 },
      { "model": "x-ai/grok-4", "average_rank": 2.75, "rankings_count": 4 },
      { "model": "google/gemini-3-pro-preview", "average_rank": 3.5, "rankings_count": 4 }
    ]
  }
}
```

---

## 7. API Layer

**File:** `backend/main.py`  
**Base URL:** `http://localhost:8001`

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/api/conversations` | List all conversations (metadata only) |
| `POST` | `/api/conversations` | Create new conversation |
| `GET` | `/api/conversations/{id}` | Get full conversation with messages |
| `POST` | `/api/conversations/{id}/message` | Send message — **returns all at once** |
| `POST` | `/api/conversations/{id}/message/stream` | Send message — **streams stage-by-stage** |

### Send Message (Batch Mode)

```
POST /api/conversations/{id}/message
Content-Type: application/json

{ "content": "What is quantum entanglement?" }
```

Waits for all 3 stages to complete, then returns the full payload in one response. Best for simple integrations.

### Send Message (Streaming Mode)

```
POST /api/conversations/{id}/message/stream
Content-Type: application/json

{ "content": "What is quantum entanglement?" }
```

Returns a Server-Sent Events (SSE) stream. The UI updates progressively as each stage finishes.

---

## 8. Streaming Protocol (SSE)

**File:** `backend/main.py → send_message_stream()`

The server yields `data: {...}\n\n` lines as each stage completes. This is standard [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).

### Event Sequence

```
data: {"type": "stage1_start"}

data: {"type": "stage1_complete", "data": [...stage1 results...]}

data: {"type": "stage2_start"}

data: {"type": "stage2_complete", "data": [...stage2 results...], "metadata": {...}}

data: {"type": "stage3_start"}

data: {"type": "stage3_complete", "data": {...stage3 result...}}

data: {"type": "title_complete", "data": {"title": "Generated conversation title"}}

data: {"type": "complete"}
```

### Event Types Reference

| Event Type | Payload | Description |
|---|---|---|
| `stage1_start` | (none) | Stage 1 is beginning |
| `stage1_complete` | `data: [stage1_results]` | All Stage 1 responses ready |
| `stage2_start` | (none) | Stage 2 is beginning |
| `stage2_complete` | `data: [stage2_results]`, `metadata: {...}` | All Stage 2 rankings + aggregate scores ready |
| `stage3_start` | (none) | Stage 3 is beginning |
| `stage3_complete` | `data: {stage3_result}` | Final synthesized answer ready |
| `title_complete` | `data: {title: string}` | Auto-generated conversation title ready |
| `complete` | (none) | All stages done, stream closing |
| `error` | `message: string` | An error occurred |

### Frontend SSE Consumption

```javascript
// frontend/src/api.js

async sendMessageStream(conversationId, content, onEvent) {
    const response = await fetch(`/api/conversations/${id}/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const event = JSON.parse(line.slice(6));
                onEvent(event.type, event);  // dispatch to App.jsx handler
            }
        }
    }
}
```

### Title Generation (Parallel with Stage 1)

The conversation title is generated **concurrently** with Stage 1 to minimize latency:

```python
# Title generation fires at the same time as Stage 1
title_task = asyncio.create_task(generate_conversation_title(request.content))

# Stage 1 runs
stage1_results = await stage1_collect_responses(request.content)

# ... stages continue ...

# Title is awaited only after stage 3, if not already done
if title_task:
    title = await title_task
```

The title is generated using `google/gemini-2.5-flash` with a 30-second timeout (fast, cheap model).

---

## 9. Anonymization & De-anonymization

### Why Anonymize?

If models knew which response was from GPT-5 or Claude, they might rank based on **brand reputation** rather than **response quality**. Anonymization enforces merit-based evaluation.

### Backend: Anonymization

```python
# Stage 2 setup in council.py

labels = [chr(65 + i) for i in range(len(stage1_results))]
# ['A', 'B', 'C', 'D'] for 4 models

label_to_model = {
    f"Response {label}": result['model']
    for label, result in zip(labels, stage1_results)
}
# {
#   "Response A": "openai/gpt-5.1",
#   "Response B": "google/gemini-3-pro-preview",
#   "Response C": "anthropic/claude-sonnet-4.5",
#   "Response D": "x-ai/grok-4"
# }
```

The `label_to_model` mapping is:
- **Created** in `stage2_collect_rankings()`
- **Returned** from `run_full_council()` in the `metadata` dict
- **Sent** to the frontend in the API response
- **NOT persisted** to storage (it's regenerated each run, or simply not needed for replayed conversations)

### Frontend: De-anonymization for Display

```javascript
// frontend/src/components/Stage2.jsx

function deAnonymizeText(text, labelToModel) {
    let result = text;
    Object.entries(labelToModel).forEach(([label, model]) => {
        const modelShortName = model.split('/')[1] || model;
        // "Response A" → "**gpt-5.1**"
        result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
    });
    return result;
}
```

The UI renders `**model-name**` as bold text via ReactMarkdown, making the display human-readable while clearly noting that the original evaluation was anonymous.

---

## 10. Ranking Parsing Algorithm

**File:** `backend/council.py → parse_ranking_from_text()`

Models are instructed to output a specific format, but output can vary. The parser handles this gracefully with fallbacks:

```python
def parse_ranking_from_text(ranking_text: str) -> List[str]:
    import re

    # PRIMARY: Look for "FINAL RANKING:" header
    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]

            # Try numbered list: "1. Response A", "2. Response B", etc.
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # FALLBACK 1: Any "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # FALLBACK 2: Scan entire text for "Response X" patterns
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches
```

### Parsing Priority

1. ✅ **Best case:** `FINAL RANKING:` section with numbered list → most reliable
2. ⚠️ **Fallback 1:** `FINAL RANKING:` section exists but no numbers → extracts in order
3. ⚠️ **Fallback 2:** No `FINAL RANKING:` header → scans whole text (less reliable)
4. ❌ **Failure:** Returns empty list `[]` (model failed to produce parseable ranking)

---

## 11. Aggregate Ranking Calculation

**File:** `backend/council.py → calculate_aggregate_rankings()`

After all 4 models rank the responses, their votes are aggregated into a **leaderboard**.

### Algorithm

```python
def calculate_aggregate_rankings(stage2_results, label_to_model):
    from collections import defaultdict

    model_positions = defaultdict(list)  # { "openai/gpt-5.1": [1, 2, 3, 1], ... }

    for ranking in stage2_results:
        parsed_ranking = parse_ranking_from_text(ranking['ranking'])

        for position, label in enumerate(parsed_ranking, start=1):
            # position 1 = best, 4 = worst
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average rank for each model
    aggregate = []
    for model, positions in model_positions.items():
        avg_rank = sum(positions) / len(positions)
        aggregate.append({
            "model": model,
            "average_rank": round(avg_rank, 2),
            "rankings_count": len(positions)  # number of peers that ranked this model
        })

    # Sort ascending: rank 1.0 is better than rank 4.0
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate
```

### Example Calculation

With 4 models voting (positions 1=best, 4=worst):

| Model | GPT-5.1 vote | Gemini vote | Claude vote | Grok vote | Average |
|---|---|---|---|---|---|
| Claude | 1 | 2 | 1 | 2 | **1.50** 🥇 |
| GPT-5.1 | 2 | 1 | 3 | 3 | **2.25** 🥈 |
| Grok-4 | 3 | 3 | 2 | 2 | **2.50** 🥉 |
| Gemini | 4 | 4 | 4 | 3 | **3.75** 4th |

**Note:** A model CAN rank itself. It doesn't know which response is its own during Stage 2 (due to anonymization).

---

## 12. Storage & Persistence

**File:** `backend/storage.py`

Conversations are stored as **individual JSON files** in `data/conversations/`.

### File Structure

```
data/
  conversations/
    {uuid}.json
    {uuid}.json
    ...
```

### Conversation JSON Schema

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-01T10:00:00.000000",
  "title": "Quantum Entanglement Explained",
  "messages": [
    {
      "role": "user",
      "content": "What is quantum entanglement?"
    },
    {
      "role": "assistant",
      "stage1": [
        { "model": "openai/gpt-5.1", "response": "..." },
        ...
      ],
      "stage2": [
        { "model": "openai/gpt-5.1", "ranking": "...", "parsed_ranking": [...] },
        ...
      ],
      "stage3": {
        "model": "google/gemini-3-pro-preview",
        "response": "..."
      }
    }
  ]
}
```

### What's NOT Persisted

- `label_to_model` mapping — ephemeral, only lives in the API response
- `aggregate_rankings` — recalculated on-the-fly, not stored
- `metadata` object — only returned in live API calls, not saved to JSON

This is a deliberate design choice: the label mapping is only needed to display Stage 2 results. Since labels are assigned deterministically (A=first response, B=second, etc.), they could be reconstructed from stored data if needed.

---

## 13. Frontend State Machine

**File:** `frontend/src/App.jsx`

The UI maintains a progressive loading state for each assistant message:

### Message State Shape

```javascript
const assistantMessage = {
  role: 'assistant',
  stage1: null,    // populated when stage1_complete fires
  stage2: null,    // populated when stage2_complete fires
  stage3: null,    // populated when stage3_complete fires
  metadata: null,  // populated along with stage2
  loading: {
    stage1: false, // true between stage1_start and stage1_complete
    stage2: false, // true between stage2_start and stage2_complete
    stage3: false, // true between stage3_start and stage3_complete
  }
};
```

### State Transitions

```
Initial state:
  { stage1: null, stage2: null, stage3: null, loading: {s1:F, s2:F, s3:F} }

After stage1_start:
  { stage1: null, stage2: null, stage3: null, loading: {s1:T, s2:F, s3:F} }

After stage1_complete:
  { stage1: [...], stage2: null, stage3: null, loading: {s1:F, s2:F, s3:F} }

After stage2_start:
  { stage1: [...], stage2: null, stage3: null, loading: {s1:F, s2:T, s3:F} }

After stage2_complete:
  { stage1: [...], stage2: [...], stage3: null, metadata: {...}, loading: {s1:F, s2:F, s3:F} }

After stage3_start:
  { stage1: [...], stage2: [...], stage3: null, metadata: {...}, loading: {s1:F, s2:F, s3:T} }

After stage3_complete:
  { stage1: [...], stage2: [...], stage3: {...}, metadata: {...}, loading: {s1:F, s2:F, s3:F} }
```

### UI Components

| Component | Renders | Data Source |
|---|---|---|
| `Stage1.jsx` | Tabbed view of each model's raw answer | `message.stage1[]` |
| `Stage2.jsx` | Tabbed evaluations + de-anonymized names + aggregate leaderboard | `message.stage2[]` + `message.metadata` |
| `Stage3.jsx` | Final synthesized answer (green background) | `message.stage3` |

---

## 14. Error Handling & Graceful Degradation

### Model-Level Failures

```python
# openrouter.py
try:
    response = await client.post(...)
    return {'content': ..., 'reasoning_details': ...}
except Exception as e:
    print(f"Error querying model {model}: {e}")
    return None  # ← None signals failure
```

### Stage-Level Handling

```python
# council.py — filter out failed models
for model, response in responses.items():
    if response is not None:  # ← Only include successful responses
        stage1_results.append(...)
```

If **all models fail** in Stage 1:
```python
if not stage1_results:
    return [], [], {"model": "error", "response": "All models failed."}, {}
```

If the **chairman fails** in Stage 3:
```python
if response is None:
    return {"model": CHAIRMAN_MODEL, "response": "Error: Unable to generate final synthesis."}
```

### Failure Scenarios Summary

| Scenario | Behavior |
|---|---|
| 1 council model fails in Stage 1 | 3 responses continue; failed model not included |
| 1 council model fails in Stage 2 | 3 rankings continue; aggregate uses available votes |
| All council models fail in Stage 1 | Returns error message, skips Stage 2 and 3 |
| Chairman fails in Stage 3 | Returns error string, stages 1 and 2 still available to user |
| SSE stream errors | `error` event emitted, frontend stops loading |

---

## 15. Complete Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  USER                                                                    │
│  Sends: "What is quantum entanglement?"                                  │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │ POST /api/conversations/{id}/message/stream
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND (main.py)                                               │
│  1. Validate conversation exists                                         │
│  2. Save user message to JSON file                                       │
│  3. Kick off asyncio SSE stream                                          │
│  4. Fire title generation task (non-blocking)                            │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼ STAGE 1 ─────────────────────────────────────
┌──────────────────────────────────────────────────────────────────────────┐
│  council.py → stage1_collect_responses()                                 │
│                                                                          │
│  asyncio.gather() fires all 4 requests simultaneously:                   │
│  ┌───────────────────────────────────────────────────────┐               │
│  │  POST openrouter.ai   POST openrouter.ai              │               │
│  │  model: gpt-5.1       model: gemini-3-pro             │               │
│  │  "What is quantum     "What is quantum                │               │
│  │   entanglement?"       entanglement?"                 │               │
│  └───────────┬───────────────────────┬───────────────────┘               │
│              │ (also grok-4, claude) │                                   │
│              ▼                       ▼                                   │
│  Each returns: { content: "..." }                                        │
│                                                                          │
│  Emit SSE: stage1_complete → [4 responses]                               │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼ STAGE 2 ─────────────────────────────────────
┌──────────────────────────────────────────────────────────────────────────┐
│  council.py → stage2_collect_rankings()                                  │
│                                                                          │
│  1. Assign labels: A=gpt-5.1, B=gemini, C=claude, D=grok                │
│  2. Build ranking prompt with anonymized responses                       │
│  3. asyncio.gather() fires all 4 ranking requests simultaneously:        │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │  Same prompt to all 4 models:                                  │      │
│  │  "Here are Response A, B, C, D... rank them best to worst"     │      │
│  └────────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  Each returns: { full eval text + FINAL RANKING section }                │
│                                                                          │
│  parse_ranking_from_text() extracts: ["Response C", "Response A", ...]   │
│  calculate_aggregate_rankings() averages all position votes              │
│                                                                          │
│  Emit SSE: stage2_complete → [4 evaluations + metadata]                  │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼ STAGE 3 ─────────────────────────────────────
┌──────────────────────────────────────────────────────────────────────────┐
│  council.py → stage3_synthesize_final()                                  │
│                                                                          │
│  Build chairman prompt:                                                  │
│  - All Stage 1 responses (WITH model names)                              │
│  - All Stage 2 evaluations (WITH model names)                            │
│  - Instructions to synthesize                                            │
│                                                                          │
│  Single query → CHAIRMAN_MODEL (gemini-3-pro)                            │
│                                                                          │
│  Returns: { model: "gemini-3-pro", response: "Final answer..." }         │
│                                                                          │
│  Emit SSE: stage3_complete → final synthesized answer                    │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼ STORAGE & COMPLETION ────────────────────────
┌──────────────────────────────────────────────────────────────────────────┐
│  1. Save full assistant message (stage1+stage2+stage3) to JSON file      │
│  2. Await title task → save title                                        │
│  3. Emit SSE: title_complete, complete                                   │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  REACT FRONTEND (App.jsx)                                                │
│                                                                          │
│  SSE events update UI progressively:                                     │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Stage1.jsx: Tab per model, shows raw answer                      │  │
│  │  Stage2.jsx: Tab per ranker, de-anonymized + aggregate leaderboard │  │
│  │  Stage3.jsx: Final answer (green tinted, prominent)               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 16. Key Design Decisions

### 1. Blind Peer Review (Anonymization)
Models receive `Response A/B/C/D` — never model names. This prevents brand-based bias and forces evaluation on content quality alone.

### 2. Parallel Execution via asyncio
Both Stage 1 and Stage 2 use `asyncio.gather()` to fire all model requests at once. This cuts latency from O(n) sequential to O(1) — total time ≈ slowest single model.

### 3. OpenRouter as Universal Gateway
All 4 heterogeneous models (OpenAI, Google, Anthropic, xAI) share one HTTP interface. Adding a new council member requires only updating the `COUNCIL_MODELS` list in `config.py`.

### 4. Strict Prompt Format for Parseable Output
The Stage 2 prompt requires `FINAL RANKING:` as a literal header with a numbered list. This structured output constraint enables reliable machine parsing, with regex fallbacks for non-compliant responses.

### 5. Ephemeral Metadata
The `label_to_model` decoder is not stored to disk — it only lives in the API response and frontend memory. This is fine because: (a) storage space is saved, (b) re-display of history doesn't require de-anonymization, (c) the mapping is trivially reconstructible.

### 6. Progressive SSE Streaming
Rather than waiting ~30 seconds for all stages, the frontend receives results as each stage completes. Users see Stage 1 responses in ~5 seconds while Stage 2 is still running.

### 7. Chairman Has Full Context
Unlike Stage 2 models who evaluate blindly, the Chairman receives named model context. This lets the Chairman reason about model-specific strengths when synthesizing (e.g., "Grok's strength in X combined with Claude's clarity on Y...").

### 8. Graceful Degradation
No single model failure can crash the system. Failed responses return `None` and are filtered out. The pipeline continues with whatever responses are available.

---

*Documentation generated from source code analysis of the LLM Council project.*  
*Backend: Python/FastAPI · Frontend: React/Vite · LLM Gateway: OpenRouter*
