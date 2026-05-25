import { useState } from "react";
import GlassCard from "@/components/GlassCard";
import StatusDot from "@/components/StatusDot";
import { api } from "@/lib/api";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Project } from "@/types/lucy";
import { FolderTree, Plus, Play, Loader2, CheckCircle2, ChevronRight, Clock, Target } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

const EMPTY_FORM = {
    name: "",
    description: "",
};

export default function Projects() {
    const queryClient = useQueryClient();
    const { data: projects = [], isLoading } = useQuery({ queryKey: ["projects"], queryFn: api.getProjects });
    const { toast } = useToast();

    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [selected, setSelected] = useState<Project | null>(null);

    const createMutation = useMutation({
        mutationFn: api.createProject,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            setShowForm(false);
            setForm(EMPTY_FORM);
            toast({ title: "Project created" });
        },
        onError: (err: Error) => toast({ title: "Error", description: err.message, variant: "destructive" }),
    });

    const executeMutation = useMutation({
        mutationFn: api.executeProject,
        onSuccess: (p) => {
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            toast({ title: "Project execution started", description: "The hierarchical plan is initiating." });
            if (selected?.id === p.id) {
                setSelected(p);
            }
        },
        onError: (err: Error) => toast({ title: "Execution failed", description: err.message, variant: "destructive" }),
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createMutation.mutate(form);
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case "active":
            case "planning": return "text-primary border-primary";
            case "completed": return "text-accent border-accent";
            case "failed": return "text-destructive border-destructive";
            default: return "text-muted-foreground border-muted-foreground";
        }
    };

    return (
        <div className="space-y-6 max-w-7xl">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-display font-bold text-foreground">Projects</h1>
                    <p className="text-sm text-muted-foreground mt-1">Manage massive hierarchical multi-agent projects</p>
                </div>
                <button onClick={() => setShowForm(true)} className="glass-button flex items-center gap-2 text-primary">
                    <Plus className="w-4 h-4" /> Create Project
                </button>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {isLoading ? (
                    <div className="col-span-3 flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-muted-foreground" /></div>
                ) : projects.length === 0 ? (
                    <div className="col-span-3 flex flex-col items-center justify-center py-16 text-muted-foreground/50">
                        <FolderTree className="w-12 h-12 mb-3" />
                        <p className="text-sm">No projects yet. Create one to kick off a hierarchical swarm.</p>
                    </div>
                ) : (
                    projects.map((project, i) => (
                        <GlassCard
                            key={project.id} glow
                            className="cursor-pointer hover:border-primary/20 transition-colors"
                            onClick={() => setSelected(project)}
                            transition={{ delay: i * 0.05 }}
                        >
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center">
                                        <FolderTree className="w-5 h-5 text-accent" />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-medium text-foreground">{project.name}</h3>
                                        <p className="text-xs text-muted-foreground line-clamp-1">{project.description}</p>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-4 flex items-center justify-between">
                                <Badge variant="outline" className={`text-[10px] capitalize ${getStatusColor(project.status)}`}>
                                    {project.status.replace("_", " ")}
                                </Badge>

                                {project.status === "pending" && (
                                    <button
                                        onClick={(e) => { e.stopPropagation(); executeMutation.mutate(project.id); }}
                                        disabled={executeMutation.isPending}
                                        className="glass-button w-8 h-8 p-0 flex items-center justify-center hover:bg-primary/20 hover:text-primary transition-colors text-muted-foreground"
                                        title="Execute Project"
                                    >
                                        {executeMutation.isPending && executeMutation.variables === project.id ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Play className="w-4 h-4 ml-0.5" />
                                        )}
                                    </button>
                                )}
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>

            <Dialog open={showForm} onOpenChange={setShowForm}>
                <DialogContent className="glass-panel-glow border-border/50 bg-card/80 backdrop-blur-xl max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-display">Create New Project</DialogTitle>
                        <DialogDescription>Define a large-scale objective for the hierarchical swarm.</DialogDescription>
                    </DialogHeader>

                    <form onSubmit={handleSubmit} className="space-y-4 mt-2">
                        <div className="space-y-1.5">
                            <label className="text-xs text-muted-foreground uppercase tracking-wider">Project Name</label>
                            <input
                                className="glass-input w-full"
                                placeholder="e.g. Migrate Auth System"
                                value={form.name}
                                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                required
                            />
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-xs text-muted-foreground uppercase tracking-wider">Project Description / Prompt</label>
                            <textarea
                                className="glass-input w-full min-h-[120px] resize-y"
                                placeholder="Describe the full objective in detail. The Planning agent will use this to break down the tasks..."
                                value={form.description}
                                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                                required
                            />
                        </div>

                        <div className="flex gap-3 pt-2">
                            <button type="button" onClick={() => setShowForm(false)} className="glass-button flex-1 text-muted-foreground text-sm">Cancel</button>
                            <button
                                type="submit"
                                disabled={createMutation.isPending || !form.name.trim() || !form.description.trim()}
                                className="glass-button flex-1 flex items-center justify-center gap-2 text-primary border-primary/20 hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed text-sm"
                            >
                                {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create Project"}
                            </button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>

            <Sheet open={!!selected} onOpenChange={() => setSelected(null)}>
                <SheetContent className="glass-panel border-l-border/50 bg-card/80 backdrop-blur-xl w-full sm:max-w-xl overflow-y-auto">
                    <SheetHeader>
                        <SheetTitle className="font-display flex justify-between items-center mr-6">
                            <span>{selected?.name}</span>
                            {selected && <Badge variant="outline" className={getStatusColor(selected.status)}>{selected.status}</Badge>}
                        </SheetTitle>
                        <SheetDescription className="whitespace-pre-wrap">{selected?.description}</SheetDescription>
                    </SheetHeader>

                    {selected && (
                        <div className="mt-8 space-y-6">
                            {selected.status === "pending" && (
                                <div className="glass-panel p-6 flex flex-col items-center justify-center text-center">
                                    <Target className="w-8 h-8 text-primary mb-3 opacity-50" />
                                    <h3 className="text-sm font-medium text-foreground mb-1">Ready for Execution</h3>
                                    <p className="text-xs text-muted-foreground mb-4">Click below to initiate the Level 0.5 Planning phase and dynamic agent allocation.</p>
                                    <button
                                        onClick={() => executeMutation.mutate(selected.id)}
                                        disabled={executeMutation.isPending}
                                        className="glass-button w-full max-w-[200px] flex items-center justify-center gap-2 text-primary bg-primary/5 hover:bg-primary/10 border-primary/20"
                                    >
                                        {executeMutation.isPending && executeMutation.variables === selected.id ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <><Play className="w-4 h-4" /> Start Project Workflow</>
                                        )}
                                    </button>
                                </div>
                            )}

                            {selected.plan && (
                                <div className="space-y-3">
                                    <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Architecture Plan</h4>
                                    <div className="glass-panel p-4 overflow-auto max-h-[300px]">
                                        <pre className="text-[10px] text-foreground font-mono">{JSON.stringify(selected.plan, null, 2)}</pre>
                                    </div>
                                </div>
                            )}

                            {selected.agent_allocation && (
                                <div className="space-y-3">
                                    <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Allocated Swarm</h4>
                                    <div className="glass-panel p-4 overflow-auto">
                                        <pre className="text-[10px] text-foreground font-mono">{JSON.stringify(selected.agent_allocation, null, 2)}</pre>
                                    </div>
                                </div>
                            )}

                            <div className="space-y-3">
                                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex justify-between">
                                    <span>Linked Tasks</span>
                                    <span>{selected.tasks?.length || 0}</span>
                                </h4>
                                {selected.tasks?.length > 0 ? (
                                    <div className="space-y-2">
                                        {selected.tasks.map(t => (
                                            <div key={t.id} className="glass-panel p-3 flex justify-between items-center">
                                                <span className="text-sm">Task #{t.id} - {t.strategy}</span>
                                                <StatusDot state={t.status === 'running' ? 'executing' : t.status as any} />
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-xs text-muted-foreground italic">No tasks initiated yet.</div>
                                )}
                            </div>
                        </div>
                    )}
                </SheetContent>
            </Sheet>
        </div>
    );
}
