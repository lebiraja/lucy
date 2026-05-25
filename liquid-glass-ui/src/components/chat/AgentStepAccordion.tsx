import { useState } from "react";
import { ChevronDown, ChevronRight, Bot, Wrench } from "lucide-react";
import type { AgentStepSummary } from "@/types/lucy";
import { ToolCallCard } from "./ToolCallCard";

const ROLE_COLORS: Record<string, string> = {
  ceo: "text-yellow-400",
  cto: "text-blue-400",
  cfo: "text-green-400",
  manager: "text-purple-400",
  developer: "text-cyan-400",
  tester: "text-orange-400",
  employee: "text-white/60",
  planner: "text-pink-400",
  questioner: "text-indigo-400",
};

interface Props {
  steps: AgentStepSummary[];
}

export function AgentStepAccordion({ steps }: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  if (!steps.length) return null;

  return (
    <div className="mt-3 space-y-1">
      <div className="text-white/40 text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1">
        <Bot className="w-3 h-3" /> Agent Steps ({steps.length})
      </div>
      {steps.map((step, i) => {
        const isOpen = openIdx === i;
        const roleColor = ROLE_COLORS[step.agent_role] || "text-white/60";
        const toolCount = step.tool_calls?.length || 0;

        return (
          <div key={i} className="rounded-lg border border-white/10 overflow-hidden">
            <button
              onClick={() => setOpenIdx(prev => prev === i ? null : i)}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-white/5 transition-colors"
            >
              <Bot className="w-3 h-3 text-white/40 flex-shrink-0" />
              <span className={`font-semibold ${roleColor}`}>[{step.agent_role}]</span>
              <span className="text-white/70">{step.agent_name}</span>
              {step.step_label && (
                <span className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-white/50">{step.step_label}</span>
              )}
              {toolCount > 0 && (
                <span className="text-[10px] text-yellow-400 flex items-center gap-0.5">
                  <Wrench className="w-2.5 h-2.5" /> {toolCount}
                </span>
              )}
              <span className="ml-auto text-white/30">{step.duration_ms}ms</span>
              <span className={`text-[10px] ${step.status === "completed" ? "text-green-400" : "text-red-400"}`}>
                {step.status === "completed" ? "✓" : "✗"}
              </span>
              {isOpen ? <ChevronDown className="w-3 h-3 text-white/40" /> : <ChevronRight className="w-3 h-3 text-white/40" />}
            </button>

            {isOpen && (
              <div className="px-3 pb-3 border-t border-white/10 space-y-2">
                {step.tool_calls?.map((tc, j) => (
                  <ToolCallCard key={j} toolCall={tc} />
                ))}
                {step.response && (
                  <div className="mt-2">
                    <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Response</div>
                    <p className="text-white/60 text-xs leading-relaxed whitespace-pre-wrap line-clamp-10">
                      {step.response}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
