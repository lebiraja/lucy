# Lucy — Hierarchical Agent System Implementation Plan

> **Historical document.** This was the phased plan for adding the hierarchical multi-agent system. That work is complete. For the current architecture see [HIERARCHICAL.md](HIERARCHICAL.md).

Implementing the [features.md](file:///home/lebi/projects/lucy/docs/features.md) spec in phases, starting with the most critical changes.

## Phase 1 — Foundation (This Session)

### UI/UX Fixes + Backend Model Upgrade

---

### UI/UX

#### [MODIFY] [AgentManager.jsx](file:///home/lebi/projects/lucy/frontend/src/components/AgentManager.jsx)
- Fix modal overflow — form gets cut off at the top when scrolled
- Reduce form height by collapsing advanced settings (temperature/max_tokens/top_p) into an expandable section
- Add proper modal scroll container

#### [MODIFY] [AgentManager.css](file:///home/lebi/projects/lucy/frontend/src/components/AgentManager.css)
- Fix modal max-height and scroll behavior
- Style the collapsible advanced settings section

---

### Backend — Hierarchical Agent Model

#### [MODIFY] [models.py](file:///home/lebi/projects/lucy/backend/app/models.py)
Add new fields to Agent model:
- `role` → enum: `CEO`, `CTO`, [Manager](file:///home/lebi/projects/lucy/frontend/src/components/AgentManager.jsx#12-274), `Employee` (replacing free-text)
- `parent_id` → self-referencing FK for hierarchy
- `operational_status` → enum: `ACTIVE`, `INACTIVE`, `PAUSED`, `STOPPED`, `FAILED`
- `infrastructure_status` → enum: `ONLINE`, `OFFLINE`  
- `state` → enum: `IDLE`, `ASSIGNED`, `PLANNING`, `DELEGATING`, `EXECUTING`, `WAITING`, `REPORTING`, `COMPLETED`, `FAILED`, `STOPPED`
- `max_iterations`, `timeout_seconds`, `last_checkpoint`
- `crash_count`, `last_heartbeat`, `avg_response_time_ms`
- `is_warm` (boolean)

#### [MODIFY] [schemas.py](file:///home/lebi/projects/lucy/backend/app/schemas.py)
- Update Agent schemas for new fields
- Add hierarchy response fields

#### [MODIFY] [agents.py](file:///home/lebi/projects/lucy/backend/app/routers/agents.py)
- Update agent CRUD for new fields
- Add `GET /api/agents/hierarchy` endpoint for tree view
- Add pause/resume/stop endpoints

---

### Frontend — Updated Agent Form & Cards

#### [MODIFY] [AgentCard.jsx](file:///home/lebi/projects/lucy/frontend/src/components/AgentCard.jsx)
- Show role badge (CEO/CTO/Manager/Employee)
- Show operational + infrastructure status
- Show agent state
- Show parent agent name

#### [MODIFY] [Dashboard.jsx](file:///home/lebi/projects/lucy/frontend/src/components/Dashboard.jsx)
- Show agent hierarchy tree view
- Show operational vs infrastructure status

---

## Phase 2 — Task Trees & Checklists (Future)
- Hierarchical task model (Project → Milestone → Feature → Task → Subtask)
- Connected checklist system
- CEO dashboard aggregation
- Controlled communication system

## Phase 3 — Advanced (Future)
- Memory system (Short-term, Long-term, Global)
- Self-healing & recovery
- Audit & logging system
- Breaker & stop mechanism

---

## Verification Plan

### After Phase 1
1. `docker compose up --build -d`
2. Verify modal scrolls properly and doesn't cut off
3. Verify agents can be created with roles (CEO/CTO/Manager/Employee)
4. Verify hierarchy (parent assignment)
5. Verify operational/infrastructure status display
