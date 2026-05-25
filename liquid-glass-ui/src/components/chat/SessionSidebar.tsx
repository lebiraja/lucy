import { useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2, MessageSquare } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Session, Strategy } from "@/types/lucy";
import { motion } from "framer-motion";

interface Props {
  sessions: Session[];
  onNewChat: () => void;
  onDelete: (id: number) => void;
  loading: boolean;
  defaultStrategy: Strategy;
}

export function SessionSidebar({ sessions, onNewChat, onDelete, loading }: Props) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const activeId = sessionId ? parseInt(sessionId) : null;

  return (
    <div className="w-64 flex-shrink-0 border-r border-white/10 bg-black/20 backdrop-blur-xl flex flex-col h-full">
      <div className="p-4 border-b border-white/10">
        <button
          onClick={onNewChat}
          disabled={loading}
          className="w-full flex items-center gap-2 px-3 py-2.5 bg-white/10 hover:bg-white/15 border border-white/15 rounded-xl text-sm text-white/80 transition-all disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
        {sessions.length === 0 && (
          <div className="text-white/30 text-xs text-center py-8">No conversations yet</div>
        )}
        {sessions.map(sess => (
          <motion.div
            key={sess.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={`group relative rounded-lg cursor-pointer transition-all ${
              activeId === sess.id
                ? "bg-white/15 border border-white/20"
                : "hover:bg-white/8 border border-transparent"
            }`}
          >
            <button
              onClick={() => navigate(`/chat/${sess.id}`)}
              className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left"
            >
              <MessageSquare className="w-3.5 h-3.5 text-white/40 flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-white/80 text-xs font-medium truncate">
                  {sess.title || "New Chat"}
                </div>
                <div className="text-white/30 text-[10px] mt-0.5">
                  {formatDistanceToNow(new Date(sess.updated_at), { addSuffix: true })}
                </div>
              </div>
            </button>
            <button
              onClick={e => { e.stopPropagation(); onDelete(sess.id); }}
              className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/20 transition-all"
            >
              <Trash2 className="w-3 h-3 text-red-400" />
            </button>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
