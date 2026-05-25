import { motion } from "framer-motion";
import { User, Bot } from "lucide-react";
import type { Message } from "@/types/lucy";
import { StructuredOutputRenderer } from "./StructuredOutputRenderer";
import { formatDistanceToNow } from "date-fns";

interface Props {
  message: Message;
  sessionId: number;
}

export function ChatMessage({ message, sessionId }: Props) {
  const isUser = message.role === "user";
  const time = formatDistanceToNow(new Date(message.created_at), { addSuffix: true });

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end gap-3 group"
      >
        <div className="max-w-[75%]">
          <div className="bg-white/10 border border-white/15 rounded-2xl rounded-tr-sm px-4 py-3">
            <p className="text-white/90 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          </div>
          <div className="text-right text-white/30 text-[10px] mt-1 pr-1">{time}</div>
        </div>
        <div className="w-8 h-8 rounded-full bg-white/10 border border-white/20 flex items-center justify-center flex-shrink-0 mt-1">
          <User className="w-4 h-4 text-white/60" />
        </div>
      </motion.div>
    );
  }

  // Assistant message
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3 group"
    >
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 border border-white/20 flex items-center justify-center flex-shrink-0 mt-1">
        <Bot className="w-4 h-4 text-blue-300" />
      </div>
      <div className="max-w-[85%] flex-1">
        <div className="bg-white/5 border border-white/10 rounded-2xl rounded-tl-sm px-4 py-4">
          {message.content === "" ? (
            <TypingIndicator />
          ) : message.structured ? (
            <StructuredOutputRenderer structured={message.structured} sessionId={sessionId} />
          ) : (
            <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
        <div className="text-white/30 text-[10px] mt-1 pl-1">{time}</div>
      </div>
    </motion.div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-white/40"
          animate={{ opacity: [0.3, 1, 0.3], y: [0, -4, 0] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </div>
  );
}
