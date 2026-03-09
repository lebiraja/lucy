import type { AgentState } from "@/types/lucy";
import { cn } from "@/lib/utils";

const stateToClass = (state: AgentState): string => {
  switch (state) {
    case "idle":
      return "status-dot-online";
    case "executing":
    case "planning":
    case "delegating":
    case "waiting":
    case "reporting":
    case "assigned":
    case "busy":
      return "status-dot-paused";
    case "paused":
      return "status-dot-paused";
    case "stopped":
    case "failed":
    case "error":
    case "completed":
      return "status-dot-offline";
    default:
      return "status-dot-offline";
  }
};

const StatusDot = ({ state, className }: { state: AgentState; className?: string }) => (
  <span className={cn(stateToClass(state), className)} />
);

export default StatusDot;
