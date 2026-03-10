# Lucy — Multi-Agent Orchestration Platform

A powerful platform to connect, manage, and orchestrate multiple LLM models running via vLLM across lab systems, with a central orchestrator agent coordinating everything.

## Quick Start

```bash
# Start everything
docker compose up -d

# Access the UI
open http://localhost:2000

# API docs (Swagger)
open http://localhost:2800/docs
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| **Frontend** | `2000` | React + Liquid Glass UI (nginx) |
| **Backend** | `2800` | FastAPI orchestrator API |
| **Database** | `2543` | PostgreSQL 16 |

## Documentation

- [Architecture & System Design](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Fixes & Implementation Notes](docs/FIXES.md)

## Orchestration Strategies

- **Sequential** — Chain agents one after another, each building on the previous response
- **Parallel** — Fan-out the prompt to all agents, then aggregate using the orchestrator
- **Dynamic** — Lucy (the orchestrator agent) analyzes the query and decides which agents to use
- **Council** — Agents give independent opinions, anonymously review peers, and CTO/CEO synthesizes
- **Hierarchical (New)** — A full Level 0-to-4 corporate hierarchy. Uses a dynamic L0.5 planning agent to allocate nodes, a CTO to break down tasks, Managers to assign checklists, and Employees to execute in parallel, bubbling back up for CEO approval. Use the `/api/projects` endpoint.

## Adding an Agent

Agents can now self-register dynamically using the REST API:
```bash
POST /api/agents/register
{
  "name": "Backend DevOps",
  "role": "manager",
  "endpoint": "http://192.168.73.41:9002",
  "capabilities": ["docker", "ci/cd"]
}
```
*Note: Agents must send periodic heartbeats to `/api/agents/heartbeat` or they will be marked offline automatically.*

Alternatively, via the Admin UI:
1. Open the admin panel at `http://localhost:2000`
2. Go to **Agents** tab
3. Click **+ Add Agent**
4. Enter the vLLM/OpenRouter endpoint, model name, and select a hierarchical role (CEO, Planner, CTO, Manager, Developer, etc).

## Environment Variables

See `.env` for configuration. Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `BACKEND_PORT`, `FRONTEND_PORT`

## Development

```bash
# Backend only
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# Frontend only (with API proxy to backend)
cd frontend && npm install && npm run dev
```

## Teardown

```bash
docker compose down       # Stop containers
docker compose down -v    # Stop + remove database volume
```





DSCS
