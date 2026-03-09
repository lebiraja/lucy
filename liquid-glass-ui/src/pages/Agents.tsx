import { useState, useEffect } from "react";
import GlassCard from "@/components/GlassCard";
import StatusDot from "@/components/StatusDot";
import { api } from "@/lib/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { AgentConfig, AgentRole } from "@/types/lucy";
import { Bot, Plus, Play, Pause, Square, Trash2, Activity, Crown, Shield, Users, User, ChevronRight } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { useToast } from "@/hooks/use-toast";

const roleIcons: Record<AgentRole, React.ElementType> = {
  ceo: Crown,
  cto: Shield,
  manager: Users,
  employee: User,
};

const roleColors: Record<AgentRole, string> = {
  ceo: "text-primary",
  cto: "text-secondary",
  manager: "text-accent",
  employee: "text-muted-foreground",
};

export default function Agents() {
  const queryClient = useQueryClient();
  const { data: agents = [] } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState<AgentConfig | null>(null);
  const { toast } = useToast();

  const [newAgent, setNewAgent] = useState({
    name: "", endpoint: "http://localhost:11434", model_name: "", role: "employee" as AgentRole,
    description: "", temperature: 0.7, max_tokens: 4096, top_p: 0.9, context_window_tokens: 32000,
  });

  const createMutation = useMutation({
    mutationFn: api.createAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setShowAdd(false);
      setNewAgent({ name: "", endpoint: "http://localhost:11434", model_name: "", role: "employee", description: "", temperature: 0.7, max_tokens: 4096, top_p: 0.9, context_window_tokens: 32000 });
      toast({ title: "Agent created" });
    },
    onError: (err) => toast({ title: "Error", description: err.message, variant: "destructive" }),
  });

  const handleAdd = () => {
    createMutation.mutate({ ...newAgent });
  };

  const statusMutation = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: "pause" | "resume" | "stop" }) => {
      switch (action) {
        case "pause": return api.pauseAgent(id);
        case "resume": return api.resumeAgent(id);
        case "stop": return api.stopAgent(id);
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });

  const toggleState = (id: number, action: "pause" | "resume" | "stop") => {
    statusMutation.mutate({ id, action });
  };

  const deleteMutation = useMutation({
    mutationFn: api.deleteAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast({ title: "Agent removed" });
    },
  });

  const removeAgent = (id: number) => deleteMutation.mutate(id);

  // Build hierarchy
  const roots = agents.filter(a => !a.parent_id);
  const childrenOf = (pid: number) => agents.filter(a => a.parent_id === pid);

  const HierarchyNode = ({ agent, depth = 0 }: { agent: AgentConfig; depth?: number }) => {
    const RoleIcon = roleIcons[agent.role];
    const children = childrenOf(agent.id);
    return (
      <div style={{ paddingLeft: depth * 24 }}>
        <div className="flex items-center gap-2 py-1.5">
          {depth > 0 && <ChevronRight className="w-3 h-3 text-muted-foreground" />}
          <StatusDot state={agent.state} />
          <RoleIcon className={`w-3.5 h-3.5 ${roleColors[agent.role]}`} />
          <span className="text-sm text-foreground">{agent.name}</span>
          {agent.is_orchestrator && <Badge className="text-[9px] bg-primary/20 text-primary border-0">Orchestrator</Badge>}
        </div>
        {children.map(c => <HierarchyNode key={c.id} agent={c} depth={depth + 1} />)}
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-7xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage your LLM agent fleet</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="glass-button flex items-center gap-2 text-primary">
          <Plus className="w-4 h-4" /> Add Agent
        </button>
      </div>

      {/* Agent grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent, i) => {
          const RoleIcon = roleIcons[agent.role];
          return (
            <GlassCard key={agent.id} glow className="cursor-pointer hover:border-primary/20 transition-colors" onClick={() => setSelected(agent)} transition={{ delay: i * 0.05 }}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center">
                    <RoleIcon className={`w-5 h-5 ${roleColors[agent.role]}`} />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{agent.name}</p>
                    <p className="text-xs text-muted-foreground">{agent.model_name}</p>
                  </div>
                </div>
                <StatusDot state={agent.state} />
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="capitalize">{agent.role}</span>
                <span>·</span>
                <span>{agent.latency_ms}ms</span>
                <span>·</span>
                <span className="capitalize">{agent.state}</span>
              </div>
              {agent.is_orchestrator && (
                <Badge className="mt-2 text-[10px] bg-primary/15 text-primary border-0">Orchestrator</Badge>
              )}
              <div className="mt-3 flex gap-1.5">
                {agent.state === "paused" || agent.state === "stopped" ? (
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); toggleState(agent.id, "resume"); }}>
                    <Play className="w-3.5 h-3.5 text-accent" />
                  </Button>
                ) : (
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); toggleState(agent.id, "pause"); }}>
                    <Pause className="w-3.5 h-3.5 text-muted-foreground" />
                  </Button>
                )}
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); toggleState(agent.id, "stop"); }}>
                  <Square className="w-3.5 h-3.5 text-muted-foreground" />
                </Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); removeAgent(agent.id); }}>
                  <Trash2 className="w-3.5 h-3.5 text-destructive" />
                </Button>
              </div>
            </GlassCard>
          );
        })}
      </div>

      {/* Hierarchy */}
      <GlassCard className="p-5">
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">Agent Hierarchy</h2>
        {roots.map(r => <HierarchyNode key={r.id} agent={r} />)}
      </GlassCard>

      {/* Add dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="glass-panel-glow border-border/50 bg-card/80 backdrop-blur-xl max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-display">Add New Agent</DialogTitle>
            <DialogDescription>Configure a new LLM agent for your fleet.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <input className="glass-input" placeholder="Agent name" value={newAgent.name} onChange={e => setNewAgent({ ...newAgent, name: e.target.value })} />
            <input className="glass-input" placeholder="Endpoint URL" value={newAgent.endpoint} onChange={e => setNewAgent({ ...newAgent, endpoint: e.target.value })} />
            <input className="glass-input" placeholder="Model name (e.g. llama3.1:8b)" value={newAgent.model_name} onChange={e => setNewAgent({ ...newAgent, model_name: e.target.value })} />
            <select className="glass-input" value={newAgent.role} onChange={e => setNewAgent({ ...newAgent, role: e.target.value as AgentRole })}>
              <option value="employee">Employee</option>
              <option value="manager">Manager</option>
              <option value="cto">CTO</option>
              <option value="ceo">CEO</option>
            </select>
            <textarea className="glass-input min-h-[80px]" placeholder="Description (optional)" value={newAgent.description} onChange={e => setNewAgent({ ...newAgent, description: e.target.value })} />
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Temperature</span><span>{newAgent.temperature.toFixed(1)}</span>
              </div>
              <Slider value={[newAgent.temperature]} onValueChange={([v]) => setNewAgent({ ...newAgent, temperature: v })} min={0} max={2} step={0.1} />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Max Tokens</span><span>{newAgent.max_tokens}</span>
              </div>
              <Slider value={[newAgent.max_tokens]} onValueChange={([v]) => setNewAgent({ ...newAgent, max_tokens: v })} min={256} max={16384} step={256} />
            </div>
            <button onClick={handleAdd} className="glass-button w-full text-primary border-primary/20 hover:border-primary/40" disabled={!newAgent.name || !newAgent.model_name}>
              Create Agent
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Detail sheet */}
      <Sheet open={!!selected} onOpenChange={() => setSelected(null)}>
        <SheetContent className="glass-panel border-l-border/50 bg-card/80 backdrop-blur-xl w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-display">{selected?.name}</SheetTitle>
            <SheetDescription>{selected?.model_name} · {selected?.role}</SheetDescription>
          </SheetHeader>
          {selected && (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "State", value: selected.state },
                  { label: "Latency", value: `${selected.latency_ms}ms` },
                  { label: "Avg Response", value: `${((selected.avg_response_time_ms ?? 0) / 1000).toFixed(1)}s` },
                  { label: "Crashes", value: selected.crash_count },
                  { label: "Temperature", value: selected.temperature },
                  { label: "Max Tokens", value: selected.max_tokens },
                  { label: "Top P", value: selected.top_p },
                  { label: "Context", value: `${((selected.context_window_tokens ?? 0) / 1000).toFixed(0)}k` },
                ].map(item => (
                  <div key={item.label} className="glass-panel p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{item.label}</p>
                    <p className="text-sm font-medium text-foreground mt-0.5">{item.value}</p>
                  </div>
                ))}
              </div>
              <div className="glass-panel p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Endpoint</p>
                <p className="text-xs text-foreground font-mono">{selected.endpoint}</p>
              </div>
              <div className="glass-panel p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Description</p>
                <p className="text-xs text-foreground leading-relaxed">{selected.description ?? "—"}</p>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
