import { useState } from "react";
import GlassCard from "@/components/GlassCard";
import StatusDot from "@/components/StatusDot";
import { api } from "@/lib/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { AgentConfig, AgentRole } from "@/types/lucy";
import {
  Bot, Plus, Play, Pause, Square, Trash2, Activity, Crown, Shield,
  Users, User, ChevronRight, Pencil, Loader2, Zap, CheckCircle2, XCircle,
  Brain, HelpCircle, Briefcase, Code, Bug
} from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { useToast } from "@/hooks/use-toast";

const roleIcons: Record<AgentRole, React.ElementType> = {
  ceo: Crown,
  cto: Shield,
  cfo: Briefcase,
  planner: Brain,
  questioner: HelpCircle,
  hr_manager: Users,
  backend_manager: Users,
  frontend_manager: Users,
  qa_manager: Users,
  manager: Users,
  developer: Code,
  tester: Bug,
  employee: User,
};

const roleColors: Record<AgentRole, string> = {
  ceo: "text-primary",
  cto: "text-secondary",
  cfo: "text-secondary",
  planner: "text-accent",
  questioner: "text-accent",
  hr_manager: "text-accent",
  backend_manager: "text-accent",
  frontend_manager: "text-accent",
  qa_manager: "text-accent",
  manager: "text-accent",
  developer: "text-muted-foreground",
  tester: "text-muted-foreground",
  employee: "text-muted-foreground",
};

const EMPTY_FORM = {
  name: "",
  endpoint: "",
  model_name: "",
  role: "employee" as AgentRole,
  parent_id: "" as number | "",
  description: "",
  is_active: true,
  is_orchestrator: false,
  temperature: 0.7,
  max_tokens: 2048,
  top_p: 0.95,
  context_window_tokens: 4096,
  max_iterations: 10,
  timeout_seconds: 300,
};
type FormState = typeof EMPTY_FORM;

export default function Agents() {
  const queryClient = useQueryClient();
  const { data: agents = [] } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const { toast } = useToast();

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentConfig | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Probe state
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<{
    success: boolean;
    model_name?: string;
    models?: string[];
    max_model_len?: number;
    recommended_max_tokens?: number;
    context_auto_detected?: boolean;
    error?: string;
  } | null>(null);

  // Detail sheet
  const [selected, setSelected] = useState<AgentConfig | null>(null);

  const updateField = <K extends keyof FormState>(field: K, value: FormState[K]) => {
    if (field === "endpoint") {
      setForm(prev => ({ ...prev, endpoint: value as string, model_name: "" }));
      setProbeResult(null);
    } else {
      setForm(prev => ({ ...prev, [field]: value }));
    }
  };

  // ── Probe / Detect ────────────────────────────────────────────────────────────
  const handleProbe = async () => {
    if (!form.endpoint.trim()) return;
    setProbing(true);
    setProbeResult(null);
    try {
      const result = await api.probeEndpoint(form.endpoint.trim());
      if (result.success && result.model_name) {
        setForm(prev => ({
          ...prev,
          model_name: result.model_name!,
          // Always apply — backend guarantees these with safe fallbacks
          context_window_tokens: result.max_model_len ?? 4096,
          max_tokens: result.recommended_max_tokens ?? 512,
        }));
      }
      setProbeResult(result);
    } catch (e: any) {
      setProbeResult({ success: false, error: e.message });
    } finally {
      setProbing(false);
    }
  };

  // ── Mutations ─────────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: api.createAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      closeForm();
      toast({ title: "Agent created" });
    },
    onError: (err: Error) => toast({ title: "Error", description: err.message, variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<AgentConfig> }) => api.updateAgent(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      closeForm();
      toast({ title: "Agent updated" });
    },
    onError: (err: Error) => toast({ title: "Error", description: err.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteAgent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast({ title: "Agent removed" });
    },
  });

  const statusMutation = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: "pause" | "resume" | "stop" }) => {
      if (action === "pause") return api.pauseAgent(id);
      if (action === "resume") return api.resumeAgent(id);
      return api.stopAgent(id);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });

  const healthAllMutation = useMutation({
    mutationFn: api.checkAllHealth,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast({ title: "Health check complete" });
    },
    onError: (err: Error) => toast({ title: "Health check failed", description: err.message, variant: "destructive" }),
  });

  // ── Form helpers ──────────────────────────────────────────────────────────────
  const closeForm = () => {
    setShowForm(false);
    setEditingAgent(null);
    setForm(EMPTY_FORM);
    setProbeResult(null);
    setShowAdvanced(false);
  };

  const openCreate = () => {
    setEditingAgent(null);
    setForm(EMPTY_FORM);
    setProbeResult(null);
    setShowAdvanced(false);
    setShowForm(true);
  };

  const openEdit = (agent: AgentConfig) => {
    setEditingAgent(agent);
    setForm({
      name: agent.name,
      endpoint: agent.endpoint,
      model_name: agent.model_name ?? "",
      role: agent.role,
      parent_id: agent.parent_id ?? "",
      description: agent.description ?? "",
      is_active: agent.is_active,
      is_orchestrator: agent.is_orchestrator,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      top_p: agent.top_p,
      context_window_tokens: agent.context_window_tokens,
      max_iterations: agent.max_iterations,
      timeout_seconds: agent.timeout_seconds,
    });
    setProbeResult(null);
    setShowAdvanced(false);
    setShowForm(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      ...form,
      parent_id: form.parent_id === "" ? null : Number(form.parent_id),
      model_name: form.model_name || undefined,
    };
    if (editingAgent) {
      updateMutation.mutate({ id: editingAgent.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  // ── Hierarchy ─────────────────────────────────────────────────────────────────
  const roots = agents.filter(a => !a.parent_id);
  const childrenOf = (pid: number) => agents.filter(a => a.parent_id === pid);
  const parentOptions = agents.filter(a => !editingAgent || a.id !== editingAgent.id);

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
          {agent.is_orchestrator && (
            <Badge className="text-[9px] bg-primary/20 text-primary border-0">Orchestrator</Badge>
          )}
        </div>
        {children.map(c => <HierarchyNode key={c.id} agent={c} depth={depth + 1} />)}
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage your LLM agent fleet</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => healthAllMutation.mutate()}
            disabled={healthAllMutation.isPending}
            className="glass-button flex items-center gap-2 text-xs text-muted-foreground"
          >
            {healthAllMutation.isPending
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Activity className="w-3.5 h-3.5" />}
            Check All
          </button>
          <button onClick={openCreate} className="glass-button flex items-center gap-2 text-primary">
            <Plus className="w-4 h-4" /> Add Agent
          </button>
        </div>
      </div>

      {/* Agent grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent, i) => {
          const RoleIcon = roleIcons[agent.role];
          return (
            <GlassCard
              key={agent.id} glow
              className="cursor-pointer hover:border-primary/20 transition-colors"
              onClick={() => setSelected(agent)}
              transition={{ delay: i * 0.05 }}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center">
                    <RoleIcon className={`w-5 h-5 ${roleColors[agent.role]}`} />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{agent.name}</p>
                    <p className="text-xs text-muted-foreground">{agent.model_name ?? "—"}</p>
                  </div>
                </div>
                <StatusDot state={agent.state} />
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="capitalize">{agent.role}</span>
                <span>·</span>
                <span>{agent.avg_response_time_ms != null ? `${(agent.avg_response_time_ms / 1000).toFixed(1)}s avg` : "—"}</span>
                <span>·</span>
                <span className="capitalize">{agent.state}</span>
              </div>
              {agent.is_orchestrator && (
                <Badge className="mt-2 text-[10px] bg-primary/15 text-primary border-0">Orchestrator</Badge>
              )}
              <div className="mt-3 flex gap-1.5">
                {agent.state === "paused" || agent.state === "stopped" ? (
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); statusMutation.mutate({ id: agent.id, action: "resume" }); }}>
                    <Play className="w-3.5 h-3.5 text-accent" />
                  </Button>
                ) : (
                  <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); statusMutation.mutate({ id: agent.id, action: "pause" }); }}>
                    <Pause className="w-3.5 h-3.5 text-muted-foreground" />
                  </Button>
                )}
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); statusMutation.mutate({ id: agent.id, action: "stop" }); }}>
                  <Square className="w-3.5 h-3.5 text-muted-foreground" />
                </Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); openEdit(agent); }}>
                  <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
                </Button>
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={e => { e.stopPropagation(); deleteMutation.mutate(agent.id); }}>
                  <Trash2 className="w-3.5 h-3.5 text-destructive" />
                </Button>
              </div>
            </GlassCard>
          );
        })}
        {agents.length === 0 && (
          <div className="col-span-3 flex flex-col items-center justify-center py-16 text-muted-foreground/50">
            <Bot className="w-12 h-12 mb-3" />
            <p className="text-sm">No agents yet — add your first one</p>
          </div>
        )}
      </div>

      {/* Hierarchy */}
      {agents.length > 0 && (
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">Agent Hierarchy</h2>
          {roots.map(r => <HierarchyNode key={r.id} agent={r} />)}
        </GlassCard>
      )}

      {/* ── Add / Edit Dialog ── */}
      <Dialog open={showForm} onOpenChange={open => { if (!open) closeForm(); }}>
        <DialogContent className="glass-panel-glow border-border/50 bg-card/80 backdrop-blur-xl max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">{editingAgent ? "Edit Agent" : "Add New Agent"}</DialogTitle>
            <DialogDescription>
              {editingAgent ? "Update this agent's configuration." : "Connect a new LLM agent to your fleet."}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            {/* Endpoint + Detect */}
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground uppercase tracking-wider">Endpoint URL</label>
              <div className="flex gap-2">
                <input
                  className="glass-input flex-1"
                  placeholder="http://192.168.1.100:11434"
                  value={form.endpoint}
                  onChange={e => updateField("endpoint", e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={handleProbe}
                  disabled={probing || !form.endpoint.trim()}
                  className="glass-button flex items-center gap-1.5 text-xs text-accent border-accent/20 hover:border-accent/40 disabled:opacity-40 disabled:cursor-not-allowed shrink-0 px-3"
                >
                  {probing
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Zap className="w-3.5 h-3.5" />}
                  {probing ? "Detecting…" : "Detect"}
                </button>
              </div>
              {probeResult && (
                <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-lg ${probeResult.success
                    ? "bg-accent/10 border border-accent/20 text-accent"
                    : "bg-destructive/10 border border-destructive/20 text-destructive"
                  }`}>
                  {probeResult.success
                    ? <>
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                      Detected: <strong>{probeResult.model_name}</strong>
                      {probeResult.max_model_len && (
                        <span className="ml-1 opacity-70">
                          · {probeResult.max_model_len.toLocaleString()} ctx
                          {!probeResult.context_auto_detected && " (default)"}
                        </span>
                      )}
                      {probeResult.models && probeResult.models.length > 1 && (
                        <span className="ml-1 opacity-70">({probeResult.models.length} models available)</span>
                      )}
                    </>
                    : <><XCircle className="w-3.5 h-3.5 shrink-0" />{probeResult.error}</>
                  }
                </div>
              )}
            </div>

            {/* Name + Role */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground uppercase tracking-wider">Name</label>
                <input
                  className="glass-input"
                  placeholder="e.g. Worker-1"
                  value={form.name}
                  onChange={e => updateField("name", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground uppercase tracking-wider">Role</label>
                <select className="glass-input" value={form.role} onChange={e => updateField("role", e.target.value as AgentRole)}>
                  <option value="employee">Employee</option>
                  <option value="developer">Developer</option>
                  <option value="tester">Tester</option>
                  <option value="manager">Manager</option>
                  <option value="backend_manager">Backend Manager</option>
                  <option value="frontend_manager">Frontend Manager</option>
                  <option value="qa_manager">QA Manager</option>
                  <option value="hr_manager">HR Manager</option>
                  <option value="planner">Planner (Level 0.5)</option>
                  <option value="questioner">Questioner (Level 0.5)</option>
                  <option value="cto">CTO</option>
                  <option value="cfo">CFO</option>
                  <option value="ceo">CEO</option>
                </select>
              </div>
            </div>

            {/* Model + Reports To */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground uppercase tracking-wider">
                  Model <span className="normal-case opacity-60">(auto-detected)</span>
                </label>
                <input
                  className={`glass-input ${form.model_name && probeResult?.success ? "border-accent/30" : ""}`}
                  placeholder="Detect or type manually"
                  value={form.model_name}
                  onChange={e => updateField("model_name", e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground uppercase tracking-wider">Reports To</label>
                <select
                  className="glass-input"
                  value={form.parent_id}
                  onChange={e => updateField("parent_id", e.target.value === "" ? "" : Number(e.target.value))}
                >
                  <option value="">None (Top Level)</option>
                  {parentOptions.map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground uppercase tracking-wider">Description</label>
              <textarea
                className="glass-input min-h-[72px] resize-none"
                placeholder="What this agent specialises in…"
                value={form.description}
                onChange={e => updateField("description", e.target.value)}
              />
            </div>

            {/* Flags */}
            <div className="flex gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox" checked={form.is_active}
                  onChange={e => updateField("is_active", e.target.checked)}
                  className="w-4 h-4 rounded accent-primary"
                />
                <span className="text-sm text-foreground">Active</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox" checked={form.is_orchestrator}
                  onChange={e => updateField("is_orchestrator", e.target.checked)}
                  className="w-4 h-4 rounded accent-primary"
                />
                <span className="text-sm text-foreground">Orchestrator Brain</span>
              </label>
            </div>

            {/* Advanced toggle */}
            <button
              type="button"
              onClick={() => setShowAdvanced(v => !v)}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
            >
              <span className={`transition-transform inline-block ${showAdvanced ? "rotate-90" : ""}`}>▶</span>
              Advanced Settings
            </button>

            {showAdvanced && (
              <div className="space-y-4 glass-panel p-4 rounded-xl">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Temperature</span><span>{form.temperature.toFixed(2)}</span>
                    </div>
                    <Slider value={[form.temperature]} onValueChange={([v]) => updateField("temperature", v)} min={0} max={2} step={0.05} />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Top P</span><span>{form.top_p.toFixed(2)}</span>
                    </div>
                    <Slider value={[form.top_p]} onValueChange={([v]) => updateField("top_p", v)} min={0} max={1} step={0.05} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs text-muted-foreground">Max Tokens</label>
                    <input type="number" min={1} max={128000} className="glass-input" value={form.max_tokens}
                      onChange={e => updateField("max_tokens", parseInt(e.target.value) || 2048)} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs text-muted-foreground">Context Window (tokens)</label>
                    <input type="number" min={512} max={1000000} className="glass-input" value={form.context_window_tokens}
                      onChange={e => updateField("context_window_tokens", parseInt(e.target.value) || 4096)} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs text-muted-foreground">Max Iterations</label>
                    <input type="number" min={1} max={1000} className="glass-input" value={form.max_iterations}
                      onChange={e => updateField("max_iterations", parseInt(e.target.value) || 10)} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs text-muted-foreground">Timeout (seconds)</label>
                    <input type="number" min={10} max={86400} className="glass-input" value={form.timeout_seconds}
                      onChange={e => updateField("timeout_seconds", parseInt(e.target.value) || 300)} />
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-1">
              <button type="button" onClick={closeForm}
                className="glass-button flex-1 text-muted-foreground text-sm">
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSaving || !form.name.trim() || !form.endpoint.trim()}
                className="glass-button flex-1 flex items-center justify-center gap-2 text-primary border-primary/20 hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed text-sm"
              >
                {isSaving
                  ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving…</>
                  : editingAgent ? "Update Agent" : "Add Agent"
                }
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Detail Sheet */}
      <Sheet open={!!selected} onOpenChange={() => setSelected(null)}>
        <SheetContent className="glass-panel border-l-border/50 bg-card/80 backdrop-blur-xl w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle className="font-display">{selected?.name}</SheetTitle>
            <SheetDescription>{selected?.model_name ?? "—"} · {selected?.role}</SheetDescription>
          </SheetHeader>
          {selected && (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "State", value: selected.state },
                  { label: "Avg Response", value: selected.avg_response_time_ms != null ? `${(selected.avg_response_time_ms / 1000).toFixed(1)}s` : "—" },
                  { label: "Crashes", value: selected.crash_count },
                  { label: "Warm", value: selected.is_warm ? "Yes" : "No" },
                  { label: "Temperature", value: selected.temperature },
                  { label: "Max Tokens", value: selected.max_tokens },
                  { label: "Top P", value: selected.top_p },
                  { label: "Context", value: `${((selected.context_window_tokens ?? 0) / 1000).toFixed(0)}k` },
                  { label: "Max Iterations", value: selected.max_iterations },
                  { label: "Timeout", value: `${selected.timeout_seconds}s` },
                ].map(item => (
                  <div key={item.label} className="glass-panel p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{item.label}</p>
                    <p className="text-sm font-medium text-foreground mt-0.5">{item.value}</p>
                  </div>
                ))}
              </div>
              <div className="glass-panel p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Endpoint</p>
                <p className="text-xs text-foreground font-mono break-all">{selected.endpoint}</p>
              </div>
              <div className="glass-panel p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Description</p>
                <p className="text-xs text-foreground leading-relaxed">{selected.description ?? "—"}</p>
              </div>
              <div className="glass-panel p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Capabilities</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {selected.capabilities?.length ? selected.capabilities.map(c => (
                    <Badge key={c} variant="outline" className="text-[10px] bg-card">{c}</Badge>
                  )) : <span className="text-xs text-muted-foreground">—</span>}
                </div>
              </div>
              <button
                onClick={() => { setSelected(null); openEdit(selected); }}
                className="glass-button w-full flex items-center justify-center gap-2 text-sm text-muted-foreground"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit Agent
              </button>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
