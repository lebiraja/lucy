import { useState, useEffect, useRef } from "react";
import GlassCard from "@/components/GlassCard";
import { api } from "@/lib/api";
import type { LogEntry, LogLevel } from "@/types/lucy";
import { Terminal, Pause, Play, Trash2, Wifi, WifiOff } from "lucide-react";
import { motion } from "framer-motion";

const levelClass: Record<LogLevel, string> = {
  info: "log-info",
  warning: "log-warning",
  error: "log-error",
  debug: "log-debug",
  agent: "log-agent",
};

const levelTag: Record<LogLevel, string> = {
  info: "INF",
  warning: "WRN",
  error: "ERR",
  debug: "DBG",
  agent: "AGT",
};

export default function Monitor() {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<LogLevel | "all">("all");
  const [clearedAt, setClearedAt] = useState(0);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  // Load historical logs on mount
  useEffect(() => {
    api.getLogs(200).then(data => setLogs(data as LogEntry[])).catch(() => {});
  }, []);

  // WebSocket for real-time streaming
  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    const ws = new WebSocket(`${proto}://${host}/api/ws/logs`);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    let wsCounter = 0;
    ws.onmessage = (event) => {
      if (pausedRef.current) return;
      try {
        const raw = JSON.parse(event.data);
        const entry: LogEntry = { id: `ws-${Date.now()}-${wsCounter++}`, ...raw };
        setLogs(prev => [...prev, entry]);
      } catch {}
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current && !paused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, paused]);

  const visibleLogs = logs.filter(l => new Date(l.timestamp).getTime() > clearedAt);
  const filtered = filter === "all" ? visibleLogs : visibleLogs.filter(l => l.level === filter);

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <div className="space-y-6 max-w-5xl h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-foreground">Live Monitor</h1>
          <p className="text-sm text-muted-foreground mt-1">Real-time system log stream</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setPaused(!paused)} className="glass-button flex items-center gap-2 text-xs">
            {paused ? <Play className="w-3.5 h-3.5 text-accent" /> : <Pause className="w-3.5 h-3.5" />}
            {paused ? "Resume" : "Pause"}
          </button>
          <button onClick={() => setClearedAt(Date.now())} className="glass-button flex items-center gap-2 text-xs">
            <Trash2 className="w-3.5 h-3.5" /> Clear
          </button>
        </div>
      </div>

      {/* Level filters */}
      <div className="flex gap-1.5">
        {(["all", "info", "warning", "error", "debug", "agent"] as const).map(l => (
          <button
            key={l}
            onClick={() => setFilter(l)}
            className={`text-xs px-2.5 py-1 rounded-md transition-colors ${filter === l ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
          >
            {l === "all" ? "All" : l.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Log terminal */}
      <GlassCard glow className="flex-1 min-h-0 p-0 flex flex-col">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/30">
          <Terminal className="w-4 h-4 text-primary" />
          <span className="text-xs text-muted-foreground font-mono">lucy://logs</span>
          <div className="ml-auto flex items-center gap-1.5">
            {wsConnected
              ? <><Wifi className="w-3 h-3 text-accent" /><span className="text-xs text-accent">live</span></>
              : <><WifiOff className="w-3 h-3 text-muted-foreground" /><span className="text-xs text-muted-foreground">offline</span></>}
            {!paused && wsConnected && (
              <motion.div
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ repeat: Infinity, duration: 1.5 }}
                className="w-2 h-2 rounded-full bg-accent ml-1"
              />
            )}
          </div>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-auto p-4 font-mono text-xs space-y-0.5 max-h-[60vh]">
          {filtered.map((log) => (
            <div key={log.id} className="flex gap-3 leading-relaxed">
              <span className="text-muted-foreground/60 shrink-0">{formatTime(log.timestamp)}</span>
              <span className={`shrink-0 w-6 ${levelClass[log.level]}`}>{levelTag[log.level]}</span>
              <span className="text-muted-foreground/50 shrink-0">[{log.source}]</span>
              <span className={`${levelClass[log.level]}`}>{log.message}</span>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="text-muted-foreground text-center py-8">No logs to display</p>
          )}
        </div>
      </GlassCard>
    </div>
  );
}
