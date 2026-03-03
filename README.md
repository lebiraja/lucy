# Lucy — Multi-Agent Orchestration Platform



A powerful platform to connect, manage, and orchestrate multiple LLM models running via vLLM across lab systems, with a central orchestrator agent (Lucy) coordinating everything.



## Quick Start

```bash
# Start everything
docker compose up --build

# Access the admin panel
open http://localhost:3000

# API docs
open http://localhost:8000/docs
```

## Architecture

| Service | Port | Description |
|---------|------|-------------|
| **Frontend** | `3000` | React admin panel (Nginx) |
| **Backend** | `8000` | FastAPI orchestrator API |
| **Database** | `5432` | PostgreSQL 16 |

## Orchestration Strategies

- **Sequential** — Chain agents one after another, each building on the previous response
- **Parallel** — Fan-out the prompt to all agents, then aggregate using the orchestrator
- **Dynamic** — Lucy (the orchestrator agent) analyzes the query and decides which agents to use

## Adding an Agent

1. Open the admin panel at `http://localhost:3000`
2. Go to **Agents** tab
3. Click **+ Add Agent**
4. Enter the vLLM endpoint (e.g., `http://192.168.73.41:9002`), model name, and role
5. Toggle **Orchestrator Brain** if this agent should be the orchestrator

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
