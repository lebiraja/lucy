import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { api } from "@/lib/api";
import type { Message, Session, Strategy, StructuredOutput } from "@/types/lucy";
import { SessionSidebar } from "@/components/chat/SessionSidebar";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";

export default function Chat() {
  const { sessionId: rawId } = useParams<{ sessionId: string }>();
  const sessionId = rawId ? parseInt(rawId) : null;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [strategy, setStrategy] = useState<Strategy>("dynamic");
  const [loading, setLoading] = useState(false);
  const [streamingMessages, setStreamingMessages] = useState<Message[]>([]);
  const [streamLog, setStreamLog] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Fetch all sessions
  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions"],
    queryFn: api.listSessions,
    refetchInterval: 5000,
  });

  // Fetch current session with messages
  const { data: currentSession } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: loading ? 1000 : false,
  });

  const messages: Message[] = currentSession?.messages || [];

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessages, streamLog]);

  const handleNewChat = useCallback(async () => {
    try {
      const sess = await api.createSession({ strategy, title: "New Chat" });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/chat/${sess.id}`);
    } catch (e) {
      console.error(e);
    }
  }, [strategy, navigate, queryClient]);

  const handleDelete = useCallback(async (id: number) => {
    await api.deleteSession(id);
    await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    if (id === sessionId) navigate("/chat");
  }, [sessionId, navigate, queryClient]);

  const handleSend = useCallback(async (content: string) => {
    if (!sessionId || loading) return;
    setLoading(true);
    setStreamLog([]);

    // Optimistically add user message
    const optimisticUser: Message = {
      id: Date.now(),
      session_id: sessionId,
      role: "user",
      content,
      structured: null,
      task_id: null,
      created_at: new Date().toISOString(),
      tool_calls: [],
    };
    // Optimistically add typing assistant message
    const optimisticAssistant: Message = {
      id: Date.now() + 1,
      session_id: sessionId,
      role: "assistant",
      content: "",
      structured: null,
      task_id: null,
      created_at: new Date().toISOString(),
      tool_calls: [],
    };
    setStreamingMessages([optimisticUser, optimisticAssistant]);

    try {
      const response = await api.sendMessage(sessionId, content);
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalMessage: Message | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "log") {
              const log = JSON.parse(event.data);
              setStreamLog(prev => [...prev.slice(-20), `[${log.level}] ${log.source}: ${log.message}`]);
            } else if (event.type === "done") {
              finalMessage = event.message as Message;
            }
          } catch {}
        }
      }

      setStreamingMessages([]);
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });

    } catch (e) {
      console.error(e);
      setStreamingMessages([]);
    } finally {
      setLoading(false);
      setStreamLog([]);
    }
  }, [sessionId, loading, queryClient]);

  // Combine persisted + streaming messages
  const displayMessages: Message[] = loading
    ? [...messages, ...streamingMessages]
    : messages;

  return (
    <div className="flex h-full">
      <SessionSidebar
        sessions={sessions}
        onNewChat={handleNewChat}
        onDelete={handleDelete}
        loading={loading}
        defaultStrategy={strategy}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {!sessionId ? (
          <EmptyState onNewChat={handleNewChat} loading={loading} />
        ) : (
          <>
            {/* Chat thread */}
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
              {displayMessages.length === 0 && !loading && (
                <div className="text-center text-white/30 text-sm mt-20">
                  Send a message to start the conversation
                </div>
              )}

              {displayMessages.map(msg => (
                <ChatMessage key={msg.id} message={msg} sessionId={sessionId} />
              ))}

              {/* Stream log (shown while waiting) */}
              {loading && streamLog.length > 0 && (
                <div className="ml-11 bg-black/30 rounded-lg border border-white/10 p-3 font-mono text-[10px] text-white/40 space-y-0.5 max-h-32 overflow-y-auto">
                  {streamLog.map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            <ChatInput
              onSend={handleSend}
              loading={loading}
              strategy={currentSession?.strategy || strategy}
              onStrategyChange={setStrategy}
            />
          </>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onNewChat, loading }: { onNewChat: () => void; loading: boolean }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center p-8">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-white/15 flex items-center justify-center">
        <Bot className="w-8 h-8 text-blue-300" />
      </div>
      <div>
        <h2 className="text-white/80 text-xl font-semibold mb-2">Lucy Multi-Agent Chat</h2>
        <p className="text-white/40 text-sm max-w-md">
          Start a conversation with your AI agent fleet. Agents can search the web, run code, generate charts, and work together across 5 orchestration strategies.
        </p>
      </div>
      <button
        onClick={onNewChat}
        disabled={loading}
        className="px-6 py-2.5 bg-blue-500/20 hover:bg-blue-500/30 border border-blue-400/30 rounded-xl text-blue-300 text-sm transition-all disabled:opacity-50"
      >
        Start New Chat
      </button>
    </div>
  );
}
