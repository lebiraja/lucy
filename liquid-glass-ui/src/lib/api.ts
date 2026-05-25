import type { AgentConfig, Task, LogEntry, SystemHealth, Project, Session, Message } from "@/types/lucy";
import type { Strategy } from "@/types/lucy";

const API_BASE = "/api";

async function handleResponse<T>(res: Response, errorMsg: string): Promise<T> {
  if (!res.ok) {
    let detail = errorMsg;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  // ---------- Agents ----------
  getAgents: () =>
    fetch(`${API_BASE}/agents`).then(r => handleResponse<AgentConfig[]>(r, "Failed to fetch agents")),

  createAgent: (agent: Partial<AgentConfig>) =>
    fetch(`${API_BASE}/agents`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(agent),
    }).then(r => handleResponse<AgentConfig>(r, "Failed to create agent")),

  updateAgent: (id: number, agent: Partial<AgentConfig>) =>
    fetch(`${API_BASE}/agents/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(agent),
    }).then(r => handleResponse<AgentConfig>(r, "Failed to update agent")),

  deleteAgent: (id: number) =>
    fetch(`${API_BASE}/agents/${id}`, { method: "DELETE" }).then(r => { if (!r.ok) throw new Error("Failed to delete agent"); }),

  pauseAgent: (id: number) =>
    fetch(`${API_BASE}/agents/${id}/pause`, { method: "POST" }).then(r => handleResponse<AgentConfig>(r, "Failed to pause agent")),

  resumeAgent: (id: number) =>
    fetch(`${API_BASE}/agents/${id}/resume`, { method: "POST" }).then(r => handleResponse<AgentConfig>(r, "Failed to resume agent")),

  stopAgent: (id: number) =>
    fetch(`${API_BASE}/agents/${id}/stop`, { method: "POST" }).then(r => handleResponse<AgentConfig>(r, "Failed to stop agent")),

  checkAgentHealth: (id: number) =>
    fetch(`${API_BASE}/agents/${id}/health`).then(r => handleResponse(r, "Failed to check agent health")),

  checkAllHealth: () =>
    fetch(`${API_BASE}/agents/health`).then(r => handleResponse(r, "Failed to check agent health")),

  probeEndpoint: (endpoint: string) =>
    fetch(`${API_BASE}/agents/probe`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint }),
    }).then(r => handleResponse<{ success: boolean; model_name?: string; models?: string[]; max_model_len?: number; recommended_max_tokens?: number; context_auto_detected?: boolean; error?: string }>(r, "Probe request failed")),

  // ---------- Sessions ----------
  createSession: (data: { title?: string; strategy?: Strategy; agent_ids?: number[] }) =>
    fetch(`${API_BASE}/sessions`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    }).then(r => handleResponse<Session>(r, "Failed to create session")),

  listSessions: () =>
    fetch(`${API_BASE}/sessions`).then(r => handleResponse<Session[]>(r, "Failed to list sessions")),

  getSession: (id: number) =>
    fetch(`${API_BASE}/sessions/${id}`).then(r => handleResponse<Session>(r, "Failed to get session")),

  deleteSession: (id: number) =>
    fetch(`${API_BASE}/sessions/${id}`, { method: "DELETE" }).then(r => { if (!r.ok) throw new Error("Failed to delete session"); }),

  listMessages: (sessionId: number) =>
    fetch(`${API_BASE}/sessions/${sessionId}/messages`).then(r => handleResponse<Message[]>(r, "Failed to list messages")),

  // Returns EventSource for SSE streaming
  sendMessage: (sessionId: number, content: string): Promise<Response> =>
    fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),

  listSessionFiles: (sessionId: number) =>
    fetch(`${API_BASE}/sessions/${sessionId}/files`).then(r => handleResponse<string[]>(r, "Failed to list files")),

  getSessionFileUrl: (sessionId: number, filename: string) =>
    `${API_BASE}/sessions/${sessionId}/files/${encodeURIComponent(filename)}`,

  // ---------- Tasks ----------
  getTasks: () =>
    fetch(`${API_BASE}/tasks`).then(r => handleResponse<Task[]>(r, "Failed to fetch tasks")),

  getTask: (id: number) =>
    fetch(`${API_BASE}/tasks/${id}`).then(r => handleResponse<Task>(r, "Failed to fetch task")),

  getTaskLogs: (id: number) =>
    fetch(`${API_BASE}/tasks/${id}/logs`).then(r => handleResponse(r, "Failed to fetch task logs")),

  createTask: (taskParams: { prompt: string; strategy: string; agent_ids?: number[] }) =>
    fetch(`${API_BASE}/tasks`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(taskParams),
    }).then(r => handleResponse<Task>(r, "Failed to create task")),

  // ---------- Projects ----------
  getProjects: () =>
    fetch(`${API_BASE}/projects`).then(r => handleResponse<Project[]>(r, "Failed to fetch projects")),

  getProject: (id: number) =>
    fetch(`${API_BASE}/projects/${id}`).then(r => handleResponse<Project>(r, "Failed to fetch project")),

  createProject: (projectParams: { name: string; description: string }) =>
    fetch(`${API_BASE}/projects`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(projectParams),
    }).then(r => handleResponse<Project>(r, "Failed to create project")),

  executeProject: (id: number) =>
    fetch(`${API_BASE}/projects/${id}/execute`, { method: "POST" }).then(r => handleResponse<Project>(r, "Failed to execute project")),

  // ---------- System ----------
  getHealth: () =>
    fetch(`${API_BASE}/health`).then(r => handleResponse<SystemHealth>(r, "Failed to fetch health")),

  getLogs: (limit = 100) =>
    fetch(`${API_BASE}/logs?limit=${limit}`).then(r => handleResponse<LogEntry[]>(r, "Failed to fetch logs")),
};
