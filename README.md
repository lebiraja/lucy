# Lucy — Conversational Multi-Agent Platform

Lucy is a persistent conversational AI platform that orchestrates multiple LLM models (via vLLM) across GPU servers. Agents work together using 5 strategies, use real tools (web search, code execution, file I/O, charts), and every conversation is saved with full history.

## Quick Start

```bash
# Copy and fill in your API keys
cp .env.example .env   # or edit .env directly

# Start everything
docker compose up -d

# Open the UI
open http://localhost:2000

# Swagger API docs
open http://localhost:2800/docs
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| **Frontend** | `2000` | React chat UI (nginx) |
| **Backend** | `2800` | FastAPI + LangGraph |
| **Database** | `2543` | PostgreSQL 16 |

## How It Works

1. Open the **Chat** page and start a conversation
2. Lucy routes your message through one of 5 orchestration strategies
3. Agents use real tools (search the web, run code, generate charts) as they work
4. Every response is structured — markdown, inline charts, tool call cards, agent step breakdowns
5. Conversations persist — pick up any session where you left off

## Orchestration Strategies

| Strategy | How it works |
|----------|-------------|
| **Dynamic** | Orchestrator agent analyzes the query and decides which agents + order |
| **Sequential** | Chain A → B → C, each agent builds on the previous response |
| **Parallel** | All agents run at once with the same prompt, orchestrator synthesizes |
| **Council** | 3-stage: individual opinions → anonymous peer review + ranking → CEO synthesis |
| **Hierarchical** | Full corporate hierarchy: CEO → Planning → CTO → Managers → Employees |

## Agent Tools

Agents can use tools during execution (permission-gated by role):

| Tool | Roles | What it does |
|------|-------|-------------|
| `web_search` | All | Google search via SerpAPI |
| `news_search` | All | Recent news via NewsAPI |
| `run_code` | CTO, Developer, Employee | Sandboxed Python (pandas, numpy, matplotlib) |
| `run_shell` | CTO, Developer, QA | Allowlist shell commands (ls, grep, cat…) |
| `read_file` / `write_file` | Most | Session-sandboxed file I/O |
| `generate_chart` | CTO, Developer, Employee | matplotlib/seaborn → inline PNG |
| `parse_csv` | CFO, Developer, Employee | pandas CSV/Excel analysis |

## Environment Variables

```env
# PostgreSQL
POSTGRES_USER=lucy
POSTGRES_PASSWORD=lucy_secret
POSTGRES_DB=lucy_db
DATABASE_URL=postgresql+asyncpg://lucy:lucy_secret@db:5432/lucy_db

# Ports
BACKEND_PORT=2800
FRONTEND_PORT=2000

# Tool API keys
SERPER_API_KEY=your_serpapi_key       # https://serpapi.com
NEWS_API_KEY=your_newsapi_key         # https://newsapi.org

# Tool settings (optional)
WORKSPACE_BASE_DIR=/tmp/lucy-workspace
CODE_EXECUTION_TIMEOUT=30
SHELL_EXECUTION_TIMEOUT=10
MAX_TOOL_ITERATIONS=5
```

## Adding Agents

In the UI → **Agents** → **+ Add Agent**. Enter the vLLM endpoint and select a role.

Or via API:
```bash
curl -X POST http://localhost:2800/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Aria",
    "endpoint": "http://192.168.73.41:9002",
    "role": "ceo",
    "is_orchestrator": true
  }'
```

Lucy auto-detects the model name from the endpoint.

## Development

```bash
# Backend (hot reload)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (Vite dev server)
cd liquid-glass-ui && npm install && npm run dev
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design, data models, request flow
- [API Reference](docs/API.md) — all endpoints with request/response schemas
- [LangGraph Engine](docs/LANGGRAPH.md) — orchestration graphs, nodes, state
- [Hierarchical Strategy](docs/HIERARCHICAL.md) — multi-level agent delegation
- [Tool System](docs/TOOLS.md) — tool registry, permissions, adding new tools

## Teardown

```bash
docker compose down          # Stop containers
docker compose down -v       # Stop + wipe database + workspace volumes
```
