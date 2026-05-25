import { useState } from "react";
import { ChevronDown, ChevronRight, AlertCircle, CheckCircle2 } from "lucide-react";
import type { ToolCallRecord } from "@/types/lucy";

const TOOL_ICONS: Record<string, string> = {
  web_search: "🔍",
  news_search: "📰",
  run_code: "⚙️",
  run_shell: "💻",
  read_file: "📄",
  write_file: "💾",
  generate_chart: "📊",
  parse_csv: "📋",
};

interface Props {
  toolCall: ToolCallRecord | {
    tool_name: string;
    agent_name: string;
    input_args: Record<string, unknown> | null;
    output: Record<string, unknown> | null;
    duration_ms: number | null;
    status: "success" | "error";
  };
}

export function ToolCallCard({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const icon = TOOL_ICONS[toolCall.tool_name] || "🔧";
  const isError = toolCall.status === "error";

  return (
    <div className={`rounded-lg border text-xs font-mono my-1 overflow-hidden ${isError ? "border-red-500/30 bg-red-950/20" : "border-white/10 bg-white/5"}`}>
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <span className="text-sm">{icon}</span>
        <span className="text-white/70 font-semibold">{toolCall.tool_name}</span>
        <span className="text-white/40 text-[10px]">via {toolCall.agent_name}</span>
        {toolCall.duration_ms && (
          <span className="ml-auto text-white/30">{toolCall.duration_ms}ms</span>
        )}
        {isError
          ? <AlertCircle className="w-3 h-3 text-red-400 ml-1" />
          : <CheckCircle2 className="w-3 h-3 text-green-400 ml-1" />
        }
        {expanded ? <ChevronDown className="w-3 h-3 text-white/40" /> : <ChevronRight className="w-3 h-3 text-white/40" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-white/10">
          {toolCall.input_args && (
            <div>
              <div className="text-white/40 text-[10px] uppercase tracking-wider mt-2 mb-1">Input</div>
              <pre className="text-white/70 text-[10px] leading-relaxed overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(toolCall.input_args, null, 2)}
              </pre>
            </div>
          )}
          {toolCall.output && (
            <div>
              <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Output</div>
              <pre className={`text-[10px] leading-relaxed overflow-x-auto whitespace-pre-wrap ${isError ? "text-red-300" : "text-white/70"}`}>
                {JSON.stringify(toolCall.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
