import { useState, useRef, KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import type { Strategy } from "@/types/lucy";

const STRATEGIES: Strategy[] = ["dynamic", "sequential", "parallel", "council", "hierarchical"];

const STRATEGY_LABELS: Record<Strategy, string> = {
  dynamic: "Dynamic",
  sequential: "Sequential",
  parallel: "Parallel",
  council: "Council",
  hierarchical: "Hierarchical",
};

interface Props {
  onSend: (content: string) => void;
  loading: boolean;
  strategy: Strategy;
  onStrategyChange: (s: Strategy) => void;
}

export function ChatInput({ onSend, loading, strategy, onStrategyChange }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <div className="border-t border-white/10 bg-black/20 backdrop-blur-xl p-4 space-y-3">
      {/* Strategy selector */}
      <div className="flex gap-1.5 flex-wrap">
        {STRATEGIES.map(s => (
          <button
            key={s}
            onClick={() => onStrategyChange(s)}
            className={`px-3 py-1 rounded-full text-[11px] font-medium transition-all ${
              strategy === s
                ? "bg-blue-500/30 border border-blue-400/50 text-blue-300"
                : "bg-white/5 border border-white/10 text-white/40 hover:text-white/60 hover:bg-white/10"
            }`}
          >
            {STRATEGY_LABELS[s]}
          </button>
        ))}
      </div>

      {/* Input row */}
      <div className="flex gap-3 items-end">
        <div className="flex-1 bg-white/5 border border-white/15 rounded-2xl px-4 py-3 focus-within:border-white/30 transition-colors">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => { setValue(e.target.value); handleInput(); }}
            onKeyDown={handleKeyDown}
            placeholder="Message the agents... (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={loading}
            className="w-full bg-transparent text-white/90 placeholder-white/30 text-sm resize-none outline-none leading-relaxed min-h-[24px] max-h-[200px] disabled:opacity-50"
          />
        </div>
        <button
          onClick={submit}
          disabled={loading || !value.trim()}
          className="w-10 h-10 rounded-full bg-blue-500 hover:bg-blue-400 disabled:bg-white/10 disabled:cursor-not-allowed flex items-center justify-center transition-all flex-shrink-0"
        >
          {loading
            ? <Loader2 className="w-4 h-4 text-white animate-spin" />
            : <Send className="w-4 h-4 text-white" />
          }
        </button>
      </div>
    </div>
  );
}
