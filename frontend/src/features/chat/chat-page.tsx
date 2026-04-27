import { useEffect, useRef, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { confirmAction, openChatStream, sendChat } from "./api";

interface Citation {
  chunk_id?: string;
  document_id?: string;
  page?: number;
  excerpt?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  pendingAction?: string | null;
  streaming?: boolean;
}

const SLASH_HELP: Record<string, string> = {
  "/plan": "Generate a test plan for the current scope.",
  "/coverage": "Show coverage matrix for the most recent plan.",
  "/source": "/source <req_id> — show the originating document chunk.",
};

export function ChatPage() {
  const { sessionId } = useParams({ strict: false }) as { sessionId: string };
  const toast = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  const ensureWs = (): WebSocket => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return wsRef.current;
    }
    const ws = openChatStream(sessionId);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as {
          token?: string;
          done?: boolean;
          error?: string;
        };
        if (data.token) {
          setMessages((msgs) => {
            const last = msgs[msgs.length - 1];
            if (!last || !last.streaming) return msgs;
            const updated: Message = { ...last, text: last.text + data.token };
            return [...msgs.slice(0, -1), updated];
          });
        }
        if (data.done) {
          setStreaming(false);
          setMessages((msgs) => {
            const last = msgs[msgs.length - 1];
            if (!last || !last.streaming) return msgs;
            return [...msgs.slice(0, -1), { ...last, streaming: false }];
          });
        }
        if (data.error) {
          setStreaming(false);
          toast.push({ title: "Stream error", description: data.error, tone: "error" });
        }
      } catch (e) {
        toast.push({
          title: "Bad WebSocket payload",
          description: (e as Error).message,
          tone: "error",
        });
      }
    };
    ws.onerror = () => {
      toast.push({ title: "WebSocket error", tone: "error" });
      setStreaming(false);
    };
    ws.onclose = () => {
      wsRef.current = null;
    };
    return ws;
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
    };
    const asstMsg: Message = {
      id: `a-${Date.now()}`,
      role: "assistant",
      text: "",
      streaming: true,
    };
    setMessages((m) => [...m, userMsg, asstMsg]);

    // Slash command path: route to non-streaming HTTP /chat so we capture
    // pending actions and citations from the structured ChatReply.
    if (text.startsWith("/")) {
      try {
        const reply = await sendChat({ session_id: sessionId, message: text });
        setMessages((m) => {
          const without = m.slice(0, -1);
          return [
            ...without,
            {
              id: asstMsg.id,
              role: "assistant",
              text: reply.assistant_message,
              pendingAction: reply.pending_action,
            },
          ];
        });
      } catch (e) {
        toast.push({
          title: "Command failed",
          description: (e as Error).message,
          tone: "error",
        });
        setMessages((m) => m.slice(0, -1));
      }
      return;
    }

    setStreaming(true);
    const ws = ensureWs();
    if (ws.readyState === WebSocket.CONNECTING) {
      await new Promise<void>((resolve, reject) => {
        ws.addEventListener("open", () => resolve(), { once: true });
        ws.addEventListener("error", () => reject(new Error("ws open failed")), { once: true });
      }).catch(() => {
        setStreaming(false);
      });
    }
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(text);
    }
  };

  const onConfirm = async (confirmed: boolean) => {
    try {
      const reply = await confirmAction(sessionId, confirmed);
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: reply.assistant_message,
          pendingAction: reply.pending_action,
        },
      ]);
    } catch (e) {
      toast.push({
        title: "Confirm failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const slashHint = input.startsWith("/")
    ? SLASH_HELP[input.split(" ")[0] ?? ""] ?? "Available: /plan /coverage /source"
    : null;

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Copilot</h1>
        <p className="text-sm text-muted-foreground">Session {sessionId}</p>
      </div>

      <Card className="flex-1 flex flex-col">
        <CardHeader>
          <CardTitle>Conversation</CardTitle>
        </CardHeader>
        <CardBody
          ref={scrollRef}
          className="flex-1 overflow-auto space-y-3"
        >
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Ask a question to get started. Try /plan or /coverage.
            </p>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} onConfirm={onConfirm} />
          ))}
        </CardBody>
        <div className="p-4 border-t border-border space-y-2">
          {slashHint && (
            <p className="text-xs text-muted-foreground">{slashHint}</p>
          )}
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask a question or /plan..."
              disabled={streaming}
            />
            <Button onClick={handleSend} disabled={streaming || !input.trim()}>
              Send
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function MessageBubble({
  message,
  onConfirm,
}: {
  message: Message;
  onConfirm: (confirmed: boolean) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div
      className={
        isUser
          ? "flex justify-end"
          : "flex justify-start"
      }
    >
      <div
        className={
          "max-w-2xl rounded-lg px-3 py-2 text-sm whitespace-pre-wrap " +
          (isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground")
        }
      >
        {message.text || (message.streaming ? "…" : "")}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.citations.map((c, i) => (
              <CitationChip key={i} citation={c} />
            ))}
          </div>
        )}
        {message.pendingAction && (
          <PendingActionBanner action={message.pendingAction} onConfirm={onConfirm} />
        )}
      </div>
    </div>
  );
}

function CitationChip({ citation }: { citation: Citation }) {
  const label =
    citation.page !== undefined
      ? `p.${citation.page}`
      : citation.chunk_id ?? "source";
  return (
    <Badge tone="info" className="cursor-pointer" title={citation.excerpt ?? ""}>
      {label}
    </Badge>
  );
}

function PendingActionBanner({
  action,
  onConfirm,
}: {
  action: string;
  onConfirm: (confirmed: boolean) => void;
}) {
  return (
    <div className="mt-3 p-2 border border-amber-300 rounded-md bg-amber-50 text-amber-900 text-xs">
      <div className="font-medium mb-2">Pending action: {action}</div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onConfirm(true)}>
          Confirm
        </Button>
        <Button size="sm" variant="outline" onClick={() => onConfirm(false)}>
          Discard
        </Button>
      </div>
    </div>
  );
}
