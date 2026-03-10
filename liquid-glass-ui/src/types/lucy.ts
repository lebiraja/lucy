export type AgentRole = "ceo" | "cto" | "cfo" | "planner" | "questioner" | "hr_manager" | "backend_manager" | "frontend_manager" | "qa_manager" | "manager" | "employee" | "developer" | "tester";
export type AgentState =
  | "idle"
  | "assigned"
  | "planning"
  | "delegating"
  | "executing"
  | "waiting"
  | "reporting"
  | "completed"
  | "failed"
  | "stopped"
  | "busy"
  | "paused"
  | "error";
export type TaskStatus = "pending" | "running" | "completed" | "failed";
export type Strategy = "sequential" | "parallel" | "dynamic" | "council" | "hierarchical";
export type LogLevel = "info" | "warning" | "error" | "debug" | "agent";

export interface AgentConfig {
  id: number;
  name: string;
  endpoint: string;
  model_name: string | null;
  role: AgentRole;
  is_orchestrator: boolean;
  parent_id: number | null;
  description: string | null;
  system_prompt?: string;
  temperature: number;
  max_tokens: number;
  top_p: number;
  context_window_tokens: number;
  max_iterations: number;
  timeout_seconds: number;
  state: AgentState;
  operational_status: string;
  infrastructure_status: string;
  is_active: boolean;
  is_warm: boolean;
  latency_ms?: number | null;
  crash_count: number;
  avg_response_time_ms: number | null;
  last_heartbeat: string | null;
  created_at: string;
  updated_at: string;
  capabilities: string[] | null;
  available_resources: any | null;
  hierarchy_level: number;
}

export interface TaskStep {
  id: number;
  task_id: number;
  agent_id: number | null;
  agent_name: string | null;
  agent_role: AgentRole | null;
  input_prompt: string;
  response: string | null;
  duration_ms: number | null;
  status: TaskStatus;
  step_label: string | null;
  created_at: string;
}

export interface CouncilMeta {
  label_to_agent: Record<string, number>;
  aggregate_rankings: {
    agent_id: number;
    agent_name: string;
    agent_role: string;
    average_rank: number;
    rankings_count: number;
    label: string;
  }[];
  reviews: { agent_id: number; agent_name: string; agent_role: string; response: string; parsed_ranking: string[] }[];
}

export interface Project {
  id: number;
  name: string;
  description: string;
  status: "pending" | "planning" | "active" | "completed" | "failed";
  plan: any | null;
  agent_allocation: any | null;
  phases: any[] | null;
  created_at: string;
  completed_at: string | null;
  tasks: Task[];
}

export interface Task {
  id: number;
  prompt: string;
  strategy: Strategy;
  status: TaskStatus;
  final_output: string | null;
  task_metadata: CouncilMeta | null;
  steps: TaskStep[];
  created_at: string;
  completed_at: string | null;
}

export interface LogEntry {
  id: string;
  level: LogLevel;
  message: string;
  source: string;
  timestamp: string;
  task_id?: string;
}

export interface SystemHealth {
  total_agents: number;
  online_agents: number;
  active_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  success_rate: number;
  uptime_seconds: number;
}
