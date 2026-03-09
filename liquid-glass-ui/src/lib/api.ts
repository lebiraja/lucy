import type { AgentConfig, Task, LogEntry, SystemHealth } from "@/types/lucy";

const API_BASE = "/api";

export const api = {
    // Agents
    getAgents: async (): Promise<AgentConfig[]> => {
        const res = await fetch(`${API_BASE}/agents`);
        if (!res.ok) throw new Error("Failed to fetch agents");
        return res.json();
    },
    createAgent: async (agent: Partial<AgentConfig>): Promise<AgentConfig> => {
        const res = await fetch(`${API_BASE}/agents`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(agent),
        });
        if (!res.ok) throw new Error("Failed to create agent");
        return res.json();
    },
    updateAgent: async (id: number, agent: Partial<AgentConfig>): Promise<AgentConfig> => {
        const res = await fetch(`${API_BASE}/agents/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(agent),
        });
        if (!res.ok) throw new Error("Failed to update agent");
        return res.json();
    },
    deleteAgent: async (id: number): Promise<void> => {
        const res = await fetch(`${API_BASE}/agents/${id}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Failed to delete agent");
    },
    pauseAgent: async (id: number): Promise<AgentConfig> => {
        const res = await fetch(`${API_BASE}/agents/${id}/pause`, { method: "POST" });
        if (!res.ok) throw new Error("Failed to pause agent");
        return res.json();
    },
    resumeAgent: async (id: number): Promise<AgentConfig> => {
        const res = await fetch(`${API_BASE}/agents/${id}/resume`, { method: "POST" });
        if (!res.ok) throw new Error("Failed to resume agent");
        return res.json();
    },
    stopAgent: async (id: number): Promise<AgentConfig> => {
        const res = await fetch(`${API_BASE}/agents/${id}/stop`, { method: "POST" });
        if (!res.ok) throw new Error("Failed to stop agent");
        return res.json();
    },
    checkAgentHealth: async (id: number) => {
        const res = await fetch(`${API_BASE}/agents/${id}/health`);
        if (!res.ok) throw new Error("Failed to check agent health");
        return res.json();
    },
    checkAllHealth: async () => {
        const res = await fetch(`${API_BASE}/agents/health`);
        if (!res.ok) throw new Error("Failed to check agent health");
        return res.json();
    },
    probeEndpoint: async (endpoint: string): Promise<{ success: boolean; model_name?: string; models?: string[]; error?: string }> => {
        const res = await fetch(`${API_BASE}/agents/probe`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint }),
        });
        if (!res.ok) throw new Error("Probe request failed");
        return res.json();
    },

    // Tasks
    getTasks: async (): Promise<Task[]> => {
        const res = await fetch(`${API_BASE}/tasks`);
        if (!res.ok) throw new Error("Failed to fetch tasks");
        return res.json();
    },
    getTask: async (id: number): Promise<Task> => {
        const res = await fetch(`${API_BASE}/tasks/${id}`);
        if (!res.ok) throw new Error("Failed to fetch task");
        return res.json();
    },
    getTaskLogs: async (id: number) => {
        const res = await fetch(`${API_BASE}/tasks/${id}/logs`);
        if (!res.ok) throw new Error("Failed to fetch task logs");
        return res.json();
    },
    createTask: async (taskParams: { prompt: string; strategy: string; agent_ids?: number[] }): Promise<Task> => {
        const res = await fetch(`${API_BASE}/tasks`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(taskParams),
        });
        if (!res.ok) throw new Error("Failed to create task");
        return res.json();
    },

    // System
    getHealth: async (): Promise<SystemHealth> => {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok) throw new Error("Failed to fetch health");
        return res.json();
    },
    getLogs: async (limit = 100): Promise<LogEntry[]> => {
        const res = await fetch(`${API_BASE}/logs?limit=${limit}`);
        if (!res.ok) throw new Error("Failed to fetch logs");
        return res.json();
    },
};
