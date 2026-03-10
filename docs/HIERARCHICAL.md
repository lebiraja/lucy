# Hierarchical Multi-Agent Architecture

**Date:** March 10, 2026
**Engine:** LangGraph

Lucy supports a full **hierarchical, multi-level agent organization**, turning the platform from a simple task executor into an autonomous virtual company. Agents are dynamically registered and assigned roles within a unified command structure.

---

## 1. Agent Hierarchy

The system models a traditional corporate hierarchy. Agents belong to specific levels, each with defined responsibilities and access scopes.

```ascii
Level 0    ┌─────────────┐
           │   CEO Agent  │  Strategic oversight, final approval
           └──────┬───────┘
                  │
Level 1    ┌──────┴──────────────────────┐
    (0.5)  │  Questioning │   Planning   │  Temporary — active during planning only
           │    Agent     │    Agent     │  Generates plan, allocates agents
           └──────┬──────────────┬───────┘
                  │              │
Level 2    ┌──────┴──────┬───────┴──────┐
           │    CTO      │     CFO      │  Technical + financial oversight
           └──────┬──────┴──────────────┘
                  │
Level 3    ┌──────┴──────────────┬───────────────┬──────────────┐
           │ Backend Mgr │ Frontend Mgr │  QA Manager  │  HR Mgr │
           │ (checklist) │ (checklist)  │  (checklist)  │         │
           └──────┬──────┴──────┬───────┴──────┬────────┘
                  │              │              │
Level 4    ┌──────┴──────┐  ┌───┴────┐    ┌────┴─────┐
           │ Developers  │  │ Devs   │    │ Testers  │
           │ (execute)   │  │(execute)│    │ (execute)│
           └─────────────┘  └────────┘    └──────────┘
```

### Roles and Levels
- **Level 0 (CEO):** Sets strategic priorities, approves final deliverables.
- **Level 1 / 0.5 (Planning):** Uses `planner` and `questioner` roles. Deconstructs client prompts, asks clarifying questions, generates architecture, and dynamically allocates agent counts.
- **Level 2 (Executives):** `cto`, `cfo`. Translates plans into technical and financial scopes.
- **Level 3 (Managers):** `manager`, `backend_manager`, `qa_manager`. Creates actionable checklists for employees.
- **Level 4 (Employees):** `employee`, `developer`, `tester`. Writes code, runs tests, executes leaves of the execution tree.

---

## 2. Dynamic Agent Discovery

Agents no longer rely on static configuration. They self-register with the platform and maintain active presence via heartbeats.

### Registration Flow
1. An agent boots up and calls `POST /api/agents/register`.
2. It provides its `name`, `role`, `endpoint`, `capabilities` (e.g., `["react", "python"]`), and `available_resources` (e.g., `{"gpu": true}`).
3. The platform auto-detects its LLM model, calculates its `hierarchy_level` based on role, and returns a `registration_token`.

### Heartbeat System
- Agents call `POST /api/agents/heartbeat` every 60 seconds using their token.
- A background task in `main.py` sweeps for stale agents every 60 seconds.
- If an agent misses heartbeats for 120 seconds, its `infrastructure_status` is automatically set to `offline`.

### Discovery
- Tasks and managers can find agents via `GET /api/agents/discover`, filtering by `role`, `capability`, `hierarchy_level`, and `is_online` status.

---

## 3. Project API and Planning Layer (Level 0.5)

To support long-running hierarchical delegation, Lucy introduces the **Project API** (`/api/projects`).

A Project represents a massive, multi-agent objective. When executed, it triggers the `hierarchical` LangGraph strategy, starting with the **Level 0.5 Planning Layer**.

```ascii
Client Request
     │
     ▼
┌─────────────────────────┐
│ POST /api/projects      │
└────────────┬────────────┘
             │
     ┌───────▼────────┐
     │  CEO Intake     │  Reviews scope, sets priorities
     └───────┬────────┘
             │
     ┌───────▼────────────────────────┐
     │  Level 0.5 Planning Layer      │
     │  ┌─────────────┐              │
     │  │ Questioning  │→ Clarify     │
     │  └──────┬──────┘   reqs       │
     │         │                      │
     │  ┌──────▼──────┐              │
     │  │  Planning    │→ Architecture│
     │  └──────┬──────┘   + phases   │
     │         │                      │
     │  ┌──────▼──────┐              │
     │  │ Allocation   │→ Agent needs │
     │  └─────────────┘              │
     └───────┬────────────────────────┘
```

The Planning Layer is a **subgraph** that operates *before* execution begins. Once the `allocation_node` determines how many agents of each role are needed, the layer deactivates, passing the detailed `project_plan` down to the CTO.

---

## 4. Hierarchical Delegation Flow

After planning, the execution flows down the organizational chart and bubbles back up for review.

```ascii
     CTO Breakdown
          │
          ▼
   Manager Delegation
     (Creates Checklists)
          │
          ▼
 Employee Execution (Fan-out)
          │
          ▼
   Manager Review  ── [Rework?] ─┐
          │                      │
          ▼                      │
   CTO Synthesis ◄───────────────┘
          │
          ▼
    CEO Approval
          │
          ▼
   Project COMPLETE
```

1. **CTO Breakdown:** The CTO translates the L0.5 JSON architecture plan into a list of technical objectives.
2. **Manager Delegation:** Managers map CTO objectives into strict, itemized checklists based on their domain (Frontend, Backend, QA).
3. **Execution Fan-Out:** `employee`, `developer`, and `tester` agents receive prompt assignments containing only their specific manager's checklist. Execution runs in parallel via `asyncio.gather()`.
4. **Manager Review:** Managers review employee output against the original checklist. If rework is needed, the graph loops back to Execution (currently limited by `rework_count` to prevent infinite loops).
5. **CTO Synthesis:** The CTO combines all reviewed departmental outputs into a unified build/deliverable.
6. **CEO Approval:** The CEO reviews the CTE synthesis against the original client prompt and strategic priorities, outputting the final executive summary.
