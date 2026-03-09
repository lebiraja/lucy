import { useState } from "react";
import GlassCard from "@/components/GlassCard";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import type { TaskStatus, Strategy } from "@/types/lucy";
import { Badge } from "@/components/ui/badge";
import { Clock, Filter, Loader2 } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const statusColors: Record<TaskStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-secondary/20 text-secondary",
  completed: "bg-accent/20 text-accent",
  failed: "bg-destructive/20 text-destructive",
};

export default function History() {
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [strategyFilter, setStrategyFilter] = useState<Strategy | "all">("all");

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.getTasks,
  });

  const filtered = tasks.filter(t =>
    (statusFilter === "all" || t.status === statusFilter) &&
    (strategyFilter === "all" || t.strategy === strategyFilter)
  );

  if (isLoading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-display font-bold text-foreground">Task History</h1>
        <p className="text-sm text-muted-foreground mt-1">Browse and inspect past task executions</p>
      </div>

      {/* Filters */}
      <GlassCard className="flex flex-wrap items-center gap-3 p-4">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <div className="flex gap-1.5">
          {(["all", "completed", "running", "pending", "failed"] as const).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors ${statusFilter === s ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
            >
              {s === "all" ? "All Status" : s}
            </button>
          ))}
        </div>
        <div className="w-px h-4 bg-border" />
        <div className="flex gap-1.5">
          {(["all", "sequential", "parallel", "dynamic", "council"] as const).map(s => (
            <button
              key={s}
              onClick={() => setStrategyFilter(s)}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors ${strategyFilter === s ? "bg-secondary/15 text-secondary" : "text-muted-foreground hover:text-foreground"}`}
            >
              {s === "all" ? "All Strategies" : s}
            </button>
          ))}
        </div>
      </GlassCard>

      {/* Task list */}
      <Accordion type="multiple" className="space-y-3">
        {filtered.map((task, i) => (
          <AccordionItem key={task.id} value={String(task.id)} className="border-0">
            <GlassCard className="p-0" transition={{ delay: i * 0.05 }}>
              <AccordionTrigger className="px-5 py-4 hover:no-underline w-full">
                <div className="flex items-start gap-3 text-left w-full">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-foreground line-clamp-1">{task.prompt}</p>
                    <div className="mt-1.5 flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="capitalize">{task.strategy}</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" />
                        {task.completed_at ? `${((new Date(task.completed_at).getTime() - new Date(task.created_at).getTime()) / 1000).toFixed(1)}s` : task.status === "running" ? "running..." : "—"}
                      </span>
                      <span>{task.steps?.length ?? 0} steps</span>
                    </div>
                  </div>
                  <Badge className={`shrink-0 text-[10px] border-0 ${statusColors[task.status]}`}>{task.status}</Badge>
                </div>
              </AccordionTrigger>
              <AccordionContent className="px-5 pb-4">
                <div className="space-y-3">
                  {task.steps.map((step, si) => (
                      <div key={si} className="glass-panel p-3 space-y-1.5">
                        <div className="flex items-center gap-2 text-xs">
                          <span className="font-mono text-muted-foreground">#{si + 1}</span>
                          <span className="font-medium text-foreground">{step.agent_name ?? "Unknown"}</span>
                          <Badge className="text-[9px] bg-muted text-muted-foreground border-0">{step.agent_role ?? step.step_label ?? ""}</Badge>
                          <span className="text-muted-foreground ml-auto">{step.duration_ms ? `${(step.duration_ms / 1000).toFixed(1)}s` : "—"}</span>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2">{step.input_prompt}</p>
                        <p className="text-sm text-foreground whitespace-pre-wrap">{step.response}</p>
                      </div>
                  ))}
                  {task.task_metadata?.aggregate_rankings && (
                    <div className="glass-panel p-3">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Council Rankings</p>
                      <div className="space-y-1">
                        {task.task_metadata.aggregate_rankings.map((r, ri) => (
                          <div key={ri} className="flex items-center justify-between text-xs">
                            <span className="text-foreground">{r.agent_name}</span>
                            <span className="text-primary font-medium">avg rank {r.average_rank}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </GlassCard>
          </AccordionItem>
        ))}
      </Accordion>

      {filtered.length === 0 && (
        <GlassCard className="text-center py-12">
          <p className="text-muted-foreground text-sm">No tasks match the selected filters</p>
        </GlassCard>
      )}
    </div>
  );
}
