import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ToolCallCard } from "./ToolCallCard";
import { AgentStepAccordion } from "./AgentStepAccordion";
import type { StructuredOutput } from "@/types/lucy";
import { FileDown, Trophy } from "lucide-react";

interface Props {
  structured: StructuredOutput;
  sessionId?: number;
}

export function StructuredOutputRenderer({ structured, sessionId }: Props) {
  const { final_answer, tool_calls, agent_steps, rankings, charts, files, strategy_used } = structured;

  return (
    <div className="space-y-4">
      {/* Strategy badge */}
      {strategy_used && (
        <span className="inline-block text-[10px] bg-white/10 text-white/50 px-2 py-0.5 rounded-full uppercase tracking-wider">
          {strategy_used}
        </span>
      )}

      {/* Final answer — markdown rendered */}
      <div className="prose prose-invert prose-sm max-w-none text-white/90">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({ className, children, ...props }) {
              const isBlock = className?.includes("language-");
              if (isBlock) {
                return (
                  <pre className="bg-black/40 rounded-lg p-3 overflow-x-auto text-xs border border-white/10">
                    <code className={className} {...props}>{children}</code>
                  </pre>
                );
              }
              return <code className="bg-white/10 px-1 py-0.5 rounded text-xs text-blue-300" {...props}>{children}</code>;
            },
            table({ children }) {
              return (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">{children}</table>
                </div>
              );
            },
            th({ children }) {
              return <th className="border border-white/20 px-3 py-2 text-left text-white/70 font-semibold bg-white/5">{children}</th>;
            },
            td({ children }) {
              return <td className="border border-white/10 px-3 py-2 text-white/60">{children}</td>;
            },
          }}
        >
          {final_answer}
        </ReactMarkdown>
      </div>

      {/* Inline charts */}
      {charts && charts.length > 0 && (
        <div className="space-y-2">
          {charts.map((b64, i) => (
            <img
              key={i}
              src={`data:image/png;base64,${b64}`}
              alt={`Chart ${i + 1}`}
              className="rounded-lg border border-white/10 max-w-full"
            />
          ))}
        </div>
      )}

      {/* Council rankings */}
      {rankings && rankings.length > 0 && (
        <div className="bg-white/5 rounded-lg border border-white/10 p-3">
          <div className="text-white/60 text-xs font-semibold mb-2 flex items-center gap-1">
            <Trophy className="w-3 h-3 text-yellow-400" /> Council Rankings
          </div>
          <div className="space-y-1">
            {rankings.map((r, i) => (
              <div key={r.agent_id} className="flex items-center gap-2 text-xs">
                <span className={`w-5 text-center font-bold ${i === 0 ? "text-yellow-400" : i === 1 ? "text-white/50" : "text-white/30"}`}>
                  #{i + 1}
                </span>
                <span className="text-white/80">{r.agent_name}</span>
                <span className="text-white/40 text-[10px]">{r.agent_role}</span>
                <span className="ml-auto text-white/40">avg rank {r.average_rank.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool calls */}
      {tool_calls && tool_calls.length > 0 && (
        <div>
          <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Tools Used ({tool_calls.length})</div>
          {tool_calls.map((tc, i) => (
            <ToolCallCard key={i} toolCall={tc} />
          ))}
        </div>
      )}

      {/* Files */}
      {files && files.length > 0 && (
        <div className="bg-white/5 rounded-lg border border-white/10 p-3">
          <div className="text-white/60 text-xs font-semibold mb-2 flex items-center gap-1">
            <FileDown className="w-3 h-3" /> Files Created
          </div>
          <div className="space-y-1">
            {files.map((f, i) => {
              const fname = f.split("/").pop() || f;
              const url = sessionId ? `/api/sessions/${sessionId}/files/${encodeURIComponent(fname)}` : "#";
              return (
                <a key={i} href={url} download={fname} className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                  <FileDown className="w-3 h-3" />
                  {fname}
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent steps */}
      {agent_steps && agent_steps.length > 0 && (
        <AgentStepAccordion steps={agent_steps} />
      )}
    </div>
  );
}
