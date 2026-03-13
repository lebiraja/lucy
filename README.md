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

## Architecture Configuration

The platform defines a rigorous hierarchical approach matching corporate boundaries:

### Data & State Layer
1. **PostgreSQL 16**: Standard relational layout storing `Projects`, `Tasks`, `Agents`, and execution status.
2. **Redis**: In-memory message bus and context storage. Short term agent memories and global project states are materialized here.

### Hierarchical Agent Roles
1. **CEO Agent (`ceo_agent.py`)**
   - **Responsibility**: System entry point. Ingests raw client requirements. Performs triage for ambiguity, scopes the boundary of the project, and accepts/rejects the Level 0.5 technical plans.
   - **Output**: `CeoAnalysisOutput`, `CeoReviewOutput`
2. **Planning Agents (`planning_agents.py`)**
   - **Responsibility**: Level 0.5 temporary agents spun up by the CEO to draft High-Level Architecture (HLA) and calculate workforce requirements (e.g., 2 Managers, 5 Employees).
   - **Output**: `PlanningOutput`
3. **CTO Agent (`cto_agent.py`)**
   - **Responsibility**: Takes the approved HLA from the CEO and translates it into specific, assignable technical Modules.
   - **Output**: `CTOStrategyOutput`
4. **Manager Agents (`manager_agent.py`)**
   - **Responsibility**: Takes Modules from the CTO and converts them into granular Tasks, defining step-by-step checklists for the Workers. Monitors worker escalations.
   - **Output**: `ManagerDelegationOutput`
5. **Worker Agents (`worker_agent.py`)**
   - **Responsibility**: Executes individual tasks. Uses tools, resolves checklists, and escalates blockages to Managers.

### Execution Engine
- **LangGraph (`workflow_engine.py`)**: Models the macroscopic project states (Intake -> Planning -> Review -> Delegation -> Execution).
- **pyautogen (`autogen_comm.py`)**: Wraps LLM GroupChats during execution. Enforces strict communication topological boundaries (Workers can only talk to Managers, Managers to CTO, etc.) and logs all discourse directly to the PostgreSQL DB.

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
