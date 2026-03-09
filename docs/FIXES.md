# Lucy — Bug Fixes & Implementation Report

## Summary

This document records all bugs found, root causes, fixes applied, and features fully implemented during the diagnostic and repair session.

---

## Critical Backend Crashes

### 1. `metadata` column name reserved by SQLAlchemy

**File:** `backend/app/models.py`  
**Severity:** 🔴 Fatal — backend could not start  
**Root cause:** The `Task` ORM model defined `metadata = Column(JSON, ...)`. SQLAlchemy's `DeclarativeBase` internally uses `metadata` as a class attribute to store table metadata. Naming a column `metadata` conflicts with this and raises `InvalidRequestError` during model import.

```
sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is reserved when using the Declarative API.
```

**Fix:** Renamed the column to `task_metadata` in:
- `backend/app/models.py` — column definition
- `backend/app/schemas.py` — `TaskResponse.task_metadata`
- `backend/app/services/orchestrator.py` — `task.task_metadata = {...}` assignment in council strategy

---

### 2. Missing `fastapi` import in `main.py`

**File:** `backend/app/main.py`  
**Severity:** 🔴 Fatal — backend could not start (masked by issue #1)  
**Root cause:** Two endpoint handlers referenced `fastapi.Depends` and `app.database.AsyncSession` as bare qualified names without importing `fastapi` or `AsyncSession` at the module level:

```python
# Before (broken)
async def health(db: app.database.AsyncSession = fastapi.Depends(app.database.get_db)):

# After (fixed)
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine, get_db

async def health(db: AsyncSession = Depends(get_db)):
```

**Fix:** Added proper imports and rewrote both endpoint signatures.

---

### 3. App startup time not tracked

**File:** `backend/app/main.py`  
**Severity:** 🟡 Minor — `uptime_seconds` always reported `0`  
**Fix:** Moved `app.state.start_time = time.time()` into the lifespan startup hook so it is set once at process start rather than on first health request.

---

### 4. Stale database schema

**Root cause:** The backend had previously started and created tables based on an older schema (before `context_window_tokens`, `avg_response_time_ms`, `is_warm`, `last_heartbeat`, `last_checkpoint` were added). SQLAlchemy's `create_all` does not alter existing tables, so these columns were missing.

**Fix:** Dropped all tables and enum types from PostgreSQL, then restarted the backend so `create_all` could recreate them fresh with the complete schema.

---

### 5. CORS origins missing frontend port

**File:** `backend/app/config.py`  
**Severity:** 🟠 High — API calls from the frontend failed with CORS errors  
**Root cause:** The allowed origins list only included `:3000` and `:5173`. The actual frontend runs on port `2000`, so cross-origin `fetch` calls were blocked.

**Fix:** Added `http://localhost:2000`, `http://127.0.0.1:2000`, `http://localhost:2800`, and `http://127.0.0.1:2800` to the CORS origins list.

---

## Frontend Crashes (Blank Page Issues)

### 6. `mockAgents` used without import in Tasks.tsx

**File:** `liquid-glass-ui/src/pages/Tasks.tsx`  
**Severity:** 🔴 Fatal — navigating to `/tasks` caused a blank page  
**Root cause:** The agent selector section used `mockAgents` (a named export from `data/mock.ts`) without importing it. This is a `ReferenceError` at runtime.

```tsx
// Before (crashed)
{mockAgents.filter(a => a.state !== "stopped").map(agent => (

// After (fixed)
{agents.filter(a => a.state !== "stopped").map(agent => (
```

**Fix:** Replaced `mockAgents` with `agents` from the existing `useQuery` call.

---

### 7. `running` variable undefined in Tasks.tsx

**File:** `liquid-glass-ui/src/pages/Tasks.tsx`  
**Severity:** 🔴 Fatal — same blank-page crash as #6  
**Root cause:** The execute button used `disabled={!prompt.trim() || running}` but `running` was never defined.

**Fix:** Replaced with `createMutation.isPending` (the correct TanStack Query v5 pending state flag).

---

### 8. AppLayout using static mock health data

**File:** `liquid-glass-ui/src/components/AppLayout.tsx`  
**Severity:** 🟠 High — header always showed hardcoded agent counts  
**Root cause:** The header displayed `mockHealth.online_agents` / `mockHealth.total_agents` from static mock data.

**Fix:** Added a `useQuery` call to `api.getHealth` with a 10-second refetch interval. The header now shows live data from the backend.

---

## Type Alignment Fixes

### 9. `AgentState` incomplete in TypeScript types

**File:** `liquid-glass-ui/src/types/lucy.ts`  
**Root cause:** The frontend `AgentState` type only included `"idle" | "busy" | "paused" | "stopped" | "error"`. The backend returns many more states from the `AgentState` enum: `assigned`, `planning`, `delegating`, `executing`, `waiting`, `reporting`, `completed`, `failed`.

**Fix:** Extended the type to include all backend enum values. Also updated `StatusDot.tsx` to use a `switch` statement covering all 13 states.

---

### 10. Agent `id` typed as `string` instead of `number`

**File:** `liquid-glass-ui/src/types/lucy.ts`  
**Root cause:** The mock data used string IDs (`"agent-001"`), causing the type to be `string`. The real backend uses PostgreSQL integer PKs.

**Fix:** Changed `AgentConfig.id` to `number`. Updated all mutation function signatures in `Agents.tsx` and `api.ts`.

---

### 11. `avg_response_time` vs `avg_response_time_ms` field mismatch

**File:** `liquid-glass-ui/src/pages/Agents.tsx`  
**Root cause:** The detail sheet accessed `selected.avg_response_time` (a legacy field from the mock Agent) but the backend returns `avg_response_time_ms`.

**Fix:** Updated all references to `avg_response_time_ms` with proper null coalescing.

---

### 12. `context_window` vs `context_window_tokens` field mismatch

**File:** `liquid-glass-ui/src/pages/Agents.tsx`  
**Root cause:** Display code used `selected.context_window` (legacy mock format). Backend returns `context_window_tokens`.

**Fix:** Updated to `context_window_tokens` throughout.

---

### 13. `total_duration_ms` not in backend schema

**Files:** `Dashboard.tsx`, `Tasks.tsx`, `History.tsx`  
**Root cause:** The frontend `Task` type had a `total_duration_ms` field. The backend does not compute or return this.

**Fix:** Computed on the frontend: `(new Date(task.completed_at).getTime() - new Date(task.created_at).getTime()) / 1000`.

---

### 14. `API_BASE` hardcoded to `localhost:2800` 

**File:** `liquid-glass-ui/src/lib/api.ts`  
**Root cause:** All API calls went directly to `http://localhost:2800/api`, bypassing the nginx reverse proxy. This requires the backend port to be accessible from the browser and breaks in container-to-container or remote access scenarios.

**Fix:** Changed `API_BASE = "/api"` to use relative URLs that route through nginx — CORS-safe, proxy-friendly.

---

### 15. `system_prompt` field not in backend schema

**File:** `liquid-glass-ui/src/pages/Agents.tsx`  
**Root cause:** The "Add Agent" form stored a `system_prompt` field. The backend `AgentCreate` schema has `description` instead.

**Fix:** Renamed the form field to `description` and updated the display sheet to show `description`.

---

### 16. History page `task.id` passed as AccordionItem value

**File:** `liquid-glass-ui/src/pages/History.tsx`  
**Root cause:** `task.id` is now a `number` but Radix `AccordionItem.value` requires a `string`.

**Fix:** Changed to `String(task.id)`.

---

## New Features Added

### Error Boundary
**File:** `liquid-glass-ui/src/components/ErrorBoundary.tsx`

Added a React class-based `ErrorBoundary` component that wraps each route in `App.tsx`. When any page component throws an unhandled error during rendering, the ErrorBoundary catches it and displays a styled error card with a "Try again" button instead of a blank white page. This is the primary fix for the page-switching blank screen issue.

---

### Extended API Client
**File:** `liquid-glass-ui/src/lib/api.ts`

Added the following missing methods:
- `updateAgent(id, data)` — `PUT /api/agents/{id}`
- `checkAgentHealth(id)` — `GET /api/agents/{id}/health`
- `checkAllHealth()` — `GET /api/agents/health`
- `getTask(id)` — `GET /api/tasks/{id}`
- `getTaskLogs(id)` — `GET /api/tasks/{id}/logs`

---

### Proper QueryClient Configuration
**File:** `liquid-glass-ui/src/App.tsx`

Added `defaultOptions` to the `QueryClient` with `retry: 1` and `staleTime: 5000ms` to prevent excessive refetching and improve UX on network errors.

---

## Known Limitations

- **No database migrations:** Schema changes require manual DROP + CREATE via `docker compose exec db psql`. Consider adding Alembic for production use.
- **No authentication:** The API has no auth layer. All endpoints are publicly accessible.
- **Context window enforcement:** Input truncation is approximate (~3.5 chars/token). Use `tiktoken` for exact token counting.
- **WebSocket reconnection:** The frontend Monitor page polls HTTP, not WebSocket. Full WS reconnection logic is not yet implemented in the UI.
