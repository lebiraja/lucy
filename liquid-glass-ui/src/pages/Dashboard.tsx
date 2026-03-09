import React from "react";
import GlassCard from "@/components/GlassCard";
import StatusDot from "@/components/StatusDot";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Bot, ListTodo, CheckCircle, TrendingUp, Clock, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import type { TaskStatus } from "@/types/lucy";
import { Badge } from "@/components/ui/badge";

const statusColors: Record<TaskStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-secondary/20 text-secondary",
  completed: "bg-accent/20 text-accent",
  failed: "bg-destructive/20 text-destructive",
};

function formatDuration(ms: number) {
  if (ms === 0 || !ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export default function Dashboard() {
  const { data: health, isLoading: healthLoading } = useQuery({ queryKey: ["health"], queryFn: api.getHealth });
  const { data: agents = [], isLoading: agentsLoading } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const { data: tasks = [], isLoading: tasksLoading } = useQuery({ queryKey: ["tasks"], queryFn: api.getTasks });

  if (healthLoading || agentsLoading || tasksLoading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const statCards = [
    { label: "Total Agents", value: health?.total_agents ?? 0, icon: Bot, color: "text-primary" },
    { label: "Active Tasks", value: health?.active_tasks ?? 0, icon: ListTodo, color: "text-secondary" },
    { label: "Completed", value: health?.completed_tasks ?? 0, icon: CheckCircle, color: "text-accent" },
    { label: "Success Rate", value: `${health?.success_rate ?? 0}%`, icon: TrendingUp, color: "text-accent" },
  ];

  return (
    <div className="space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-display font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">System overview and agent status</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s, i) => (
          <GlassCard key={s.label} glow transition={{ delay: i * 0.08 }}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">{s.label}</p>
                <p className="text-3xl font-display font-bold mt-1 text-foreground">{s.value}</p>
              </div>
              <s.icon className={`w-5 h-5 ${s.color} opacity-70`} />
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Agent grid */}
        <div className="lg:col-span-3 space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Agent Status</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {agents.map((agent, i) => (
              <GlassCard key={agent.id} className="p-4" transition={{ delay: i * 0.06 }}>
                <div className="flex items-center gap-3">
                  <StatusDot state={agent.state} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{agent.name}</p>
                    <p className="text-xs text-muted-foreground">{agent.model_name || "Unknown Model"}</p>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground px-2 py-0.5 rounded-full bg-muted/50">
                    {agent.role}
                  </span>
                </div>
                <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                  <span>{agent.avg_response_time_ms ? `${(agent.avg_response_time_ms / 1000).toFixed(1)}s avg` : "no data"}</span>
                  {agent.crash_count > 0 && (
                    <span className="text-destructive">{agent.crash_count} crashes</span>
                  )}
                </div>
              </GlassCard>
            ))}
            {agents.length === 0 && (
              <p className="text-xs text-muted-foreground col-span-2 py-4">No agents registered.</p>
            )}
          </div>
        </div>

        {/* Recent tasks */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Recent Tasks</h2>
          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
            {tasks.slice(0, 10).map((task, i) => (
              <GlassCard key={task.id} className="p-4" transition={{ delay: i * 0.06 }}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-foreground line-clamp-2">{task.prompt}</p>
                  <Badge className={`shrink-0 text-[10px] ${statusColors[task.status]} border-0`}>
                    {task.status}
                  </Badge>
                </div>
                <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="capitalize">{task.strategy}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {task.completed_at ? `${((new Date(task.completed_at).getTime() - new Date(task.created_at).getTime()) / 1000).toFixed(1)}s` : task.status === "running" ? "running..." : "—"}
                  </span>
                  <span>{task.steps?.length ?? 0} steps</span>
                </div>
              </GlassCard>
            ))}
            {tasks.length === 0 && (
              <p className="text-xs text-muted-foreground py-4">No recent tasks.</p>
            )}
          </div>
        </div>
      </div>

      {/* Heartbeat */}
      <GlassCard className="flex items-center gap-3 p-4">
        <motion.div
          animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="w-2.5 h-2.5 rounded-full bg-accent"
        />
        <span className="text-xs text-muted-foreground">
          System online · Uptime {Math.floor((health?.uptime_seconds ?? 0) / 3600)}h {Math.floor(((health?.uptime_seconds ?? 0) % 3600) / 60)}m
        </span>
      </GlassCard>
    </div>
  );
}
