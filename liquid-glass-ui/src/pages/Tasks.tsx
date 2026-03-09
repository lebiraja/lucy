import React, { useState } from "react";
import GlassCard from "@/components/GlassCard";
import { api } from "@/lib/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Strategy, Task } from "@/types/lucy";
import { Play, Zap, GitBranch, Users, Layers, Loader2, CheckCircle, XCircle, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useToast } from "@/hooks/use-toast";
import { motion, AnimatePresence } from "framer-motion";

const strategies: { value: Strategy; label: string; icon: React.ElementType; desc: string }[] = [
  { value: "sequential", label: "Sequential", icon: Layers, desc: "Agents run one after another" },
  { value: "parallel", label: "Parallel", icon: Zap, desc: "All agents run simultaneously" },
  { value: "dynamic", label: "Dynamic", icon: GitBranch, desc: "Orchestrator decides routing" },
  { value: "council", label: "Council", icon: Users, desc: "Agents vote and synthesize" },
];

export default function Tasks() {
  const queryClient = useQueryClient();
  const { data: agents = [] } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const [prompt, setPrompt] = useState("");
  const [strategy, setStrategy] = useState<Strategy>("sequential");
  const [selectedAgents, setSelectedAgents] = useState<number[]>([]);
  const [trackingId, setTrackingId] = useState<number | null>(null);
  const { toast } = useToast();

  // Poll GET /api/tasks/:id until the task reaches a terminal state
  const { data: liveTask } = useQuery<Task>({
    queryKey: ["task", trackingId],
    queryFn: () => api.getTask(trackingId!),
    enabled: trackingId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed") return false;
      return 2000;
    },
  });

  const toggleAgent = (id: number) => {
    setSelectedAgents(prev => prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]);
  };

  const createMutation = useMutation({
    mutationFn: api.createTask,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
      setTrackingId(data.id);
      toast({ title: "Task queued", description: "Waiting for agents…" });
      setPrompt("");
    },
    onError: (err) => toast({ title: "Error", description: err.message, variant: "destructive" }),
  });

  const handleExecute = () => {
    if (!prompt.trim()) return;

    const agentIds = selectedAgents.length > 0 ? selectedAgents : undefined;
    createMutation.mutate({ prompt, strategy, agent_ids: agentIds });
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-display font-bold text-foreground">New Task</h1>
        <p className="text-sm text-muted-foreground mt-1">Create and execute a multi-agent task</p>
      </div>

      {/* Prompt */}
      <GlassCard glow>
        <textarea
          className="glass-input min-h-[120px] resize-none text-base"
          placeholder="Describe the task you want your agents to accomplish..."
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
        />
      </GlassCard>

      {/* Strategy */}
      <div className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Strategy</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {strategies.map(s => (
            <button
              key={s.value}
              onClick={() => setStrategy(s.value)}
              className={`glass-panel p-4 text-left transition-all duration-300 ${strategy === s.value
                ? "border-primary/30 shadow-[0_0_20px_-5px_hsla(var(--glass-glow))]"
                : "hover:border-border/40"
                }`}
            >
              <s.icon className={`w-5 h-5 mb-2 ${strategy === s.value ? "text-primary" : "text-muted-foreground"}`} />
              <p className={`text-sm font-medium ${strategy === s.value ? "text-foreground" : "text-muted-foreground"}`}>{s.label}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{s.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Agent selection */}
      <div className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Agents <span className="text-muted-foreground/60">(optional — leave empty for all active)</span>
        </h2>
        <div className="flex flex-wrap gap-2">
          {agents.filter(a => a.state !== "stopped").map(agent => (
            <button
              key={agent.id}
              onClick={() => toggleAgent(agent.id)}
              className={`glass-panel px-3 py-2 text-xs transition-all duration-200 flex items-center gap-2 ${selectedAgents.includes(agent.id) ? "border-primary/30 text-foreground" : "text-muted-foreground"
                }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${selectedAgents.includes(agent.id) ? "bg-primary" : "bg-muted-foreground/40"}`} />
              {agent.name}
            </button>
          ))}
        </div>
      </div>

      {/* Execute */}
      <button
        onClick={handleExecute}
        disabled={!prompt.trim() || createMutation.isPending}
        className="glass-button flex items-center gap-2 text-primary border-primary/20 hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed w-full justify-center py-3 text-base"
      >
        {createMutation.isPending ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" /> Running...
          </>
        ) : (
          <>
            <Play className="w-4 h-4" /> Execute Task
          </>
        )}
      </button>

      {/* Results */}
      <AnimatePresence>
        {trackingId !== null && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            {/* Status header */}
            <div className="flex items-center gap-2">
              {!liveTask || liveTask.status === "pending" || liveTask.status === "running" ? (
                <Loader2 className="w-4 h-4 animate-spin text-secondary" />
              ) : liveTask.status === "completed" ? (
                <CheckCircle className="w-4 h-4 text-accent" />
              ) : (
                <XCircle className="w-4 h-4 text-destructive" />
              )}
              <h2 className="text-sm font-medium text-foreground">Task Result</h2>
              {liveTask && (
                <Badge className={`border-0 text-[10px] ${
                  liveTask.status === "completed" ? "bg-accent/20 text-accent" :
                  liveTask.status === "failed" ? "bg-destructive/20 text-destructive" :
                  liveTask.status === "running" ? "bg-secondary/20 text-secondary" :
                  "bg-muted text-muted-foreground"
                }`}>{liveTask.status}</Badge>
              )}
              <span className="text-xs text-muted-foreground ml-auto flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {liveTask?.completed_at
                  ? `${((new Date(liveTask.completed_at).getTime() - new Date(liveTask.created_at).getTime()) / 1000).toFixed(1)}s total`
                  : liveTask?.status === "running" ? "running…" : "queued…"}
              </span>
            </div>

            {/* Running placeholder */}
            {(!liveTask || liveTask.status === "pending" || liveTask.status === "running") && (
              <GlassCard className="flex items-center gap-3 py-6 justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
                <span className="text-sm text-muted-foreground">
                  {liveTask?.status === "running"
                    ? `Running… ${liveTask.steps.length} step${liveTask.steps.length !== 1 ? "s" : ""} so far`
                    : "Queuing task…"}
                </span>
              </GlassCard>
            )}

            {/* Final output */}
            {liveTask?.final_output && (
              <GlassCard className="p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Final Output</p>
                <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{liveTask.final_output}</p>
              </GlassCard>
            )}

            {/* Steps */}
            {liveTask && liveTask.steps.length > 0 && (
              <Accordion type="multiple" className="space-y-2">
                {liveTask.steps.map((step, i) => (
                  <AccordionItem key={i} value={`step-${i}`} className="glass-panel border-border/30">
                    <AccordionTrigger className="px-4 py-3 hover:no-underline">
                      <div className="flex items-center gap-3 text-left">
                        <span className="text-xs text-muted-foreground font-mono">#{i + 1}</span>
                        <span className="text-sm font-medium text-foreground">{step.agent_name ?? "Unknown"}</span>
                        <Badge className="text-[9px] bg-muted text-muted-foreground border-0">{step.agent_role ?? step.step_label ?? ""}</Badge>
                        <span className="text-xs text-muted-foreground ml-auto mr-2">{step.duration_ms ? `${(step.duration_ms / 1000).toFixed(1)}s` : "—"}</span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-4 pb-4">
                      <div className="space-y-2">
                        <div>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Input</p>
                          <p className="text-xs text-muted-foreground">{step.input_prompt}</p>
                        </div>
                        <div>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Response</p>
                          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{step.response}</p>
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
