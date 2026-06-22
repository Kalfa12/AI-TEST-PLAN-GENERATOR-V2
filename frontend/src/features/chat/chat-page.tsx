import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { confirmAction, getChatContext, getChatHistory, sendChat } from "./api";
import {
  createSession,
  getSession,
  touchSession,
} from "@/lib/chat-sessions";
import type { ChatContextSummary } from "@/lib/api/types";

export interface Citation {
  chunk_id?: string;
  document_id?: string;
  page?: number;
  excerpt?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  pendingAction?: string | null;
  pendingActionId?: string | null;
  pendingActionPreview?: string | null;
  unsupportedAction?: string | null;
  streaming?: boolean;
}

const SLASH_HELP: Record<string, string> = {
  "/plan": "Generate a test plan for the current scope.",
  "/coverage": "Show coverage matrix for the most recent plan.",
  "/source": "/source <req_id> — show the originating document chunk.",
};

export function ChatPage() {
  const { sessionId } = useParams({ strict: false }) as { sessionId: string };
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const session = getSession(sessionId);
  const projectId = session?.projectId;
  const chatContext = useQuery({
    queryKey: ["chat-context", projectId],
    queryFn: () => getChatContext(projectId as string),
    enabled: Boolean(projectId),
    staleTime: 10_000,
  });

  const onNewChat = () => {
    if (!projectId) {
      toast.push({
        title: "No project context",
        description: "Open this chat from a project dashboard to start a new one.",
        tone: "error",
      });
      return;
    }
    const s = createSession(projectId);
    navigate({ to: "/chat/$sessionId", params: { sessionId: s.id } });
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  useEffect(() => {
    if (!streaming) inputRef.current?.focus();
  }, [streaming]);

  // Restore conversation on mount or whenever the session id changes.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const hist = await getChatHistory(sessionId, projectId);
        if (cancelled) return;
        const restored: Message[] = hist.events
          .filter(
            (e) =>
              e.kind === "message" &&
              (e.actor === "user" || e.actor === "assistant" || e.actor === "copilot"),
          )
          .map((e, i) => ({
            id: `h-${i}-${e.ts}`,
            role: e.actor === "user" ? "user" : "assistant",
            text: e.content,
          }));
        if (restored.length > 0) setMessages(restored);
      } catch {
        // No history yet — fresh session, fine.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, sessionId]);

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

    // Refresh the localStorage session record (sets title from first
    // message and bumps updatedAt so the dashboard list re-orders).
    touchSession(sessionId, text);

    setStreaming(true);
    try {
      const reply = await sendChat({
        session_id: sessionId,
        project_id: projectId,
        message: text,
      });
      setMessages((m) => {
        const without = m.slice(0, -1);
        return [
          ...without,
          {
            id: asstMsg.id,
            role: "assistant",
            text: reply.assistant_message,
            pendingAction: reply.pending_action,
            pendingActionId: reply.pending_action_id,
            pendingActionPreview: reply.pending_action_preview,
            unsupportedAction: reply.unsupported_action,
          },
        ];
      });
    } catch (e) {
      toast.push({
        title: text.startsWith("/") ? "Command failed" : "Chat failed",
        description: (e as Error).message,
        tone: "error",
      });
      setMessages((m) => m.slice(0, -1));
    } finally {
      setStreaming(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const onConfirm = async (confirmed: boolean, actionId?: string | null) => {
    try {
      const reply = await confirmAction(sessionId, confirmed, actionId);
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: reply.assistant_message,
          pendingAction: reply.pending_action,
          unsupportedAction: reply.unsupported_action,
        },
      ]);
      if (projectId) {
        void queryClient.invalidateQueries({ queryKey: ["chat-context", projectId] });
      }
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
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            {session?.title ?? "Copilot"}
          </h1>
          <p className="text-sm text-muted-foreground font-mono">{sessionId}</p>
          {projectId && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Project: <span className="font-mono">{projectId}</span>
            </p>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={onNewChat}>
          New chat
        </Button>
      </div>

      <ChatContextIndicator
        context={chatContext.data}
        loading={chatContext.isLoading}
        error={chatContext.isError}
        hasProject={Boolean(projectId)}
      />

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
              ref={inputRef}
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

export function MessageBubble({
  message,
  onConfirm,
}: {
  message: Message;
  onConfirm: (confirmed: boolean, actionId?: string | null) => void;
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
          <PendingActionBanner
            action={message.pendingAction}
            actionId={message.pendingActionId}
            preview={message.pendingActionPreview}
            onConfirm={onConfirm}
          />
        )}
        {message.unsupportedAction && (
          <UnsupportedActionNotice action={message.unsupportedAction} />
        )}
      </div>
    </div>
  );
}

function ChatContextIndicator({
  context,
  loading,
  error,
  hasProject,
}: {
  context?: ChatContextSummary;
  loading: boolean;
  error: boolean;
  hasProject: boolean;
}) {
  if (!hasProject) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        No project context attached
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-md border border-border bg-surface px-4 py-3 text-sm text-muted-foreground">
        Loading chat context...
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        Chat context unavailable
      </div>
    );
  }

  const latest = context.latest_plan;
  return (
    <div className="rounded-md border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">Chat context</span>
        <Badge tone="info">{context.project_name}</Badge>
        <Badge>{context.industry}</Badge>
        <Badge tone={context.documents > 0 ? "success" : "warning"}>
          {context.documents} docs
        </Badge>
        <Badge tone={context.requirements > 0 ? "success" : "warning"}>
          {context.requirements} requirements
        </Badge>
        <Badge tone={context.plans > 0 ? "success" : "warning"}>
          {context.plans} plans
        </Badge>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        Latest plan:{" "}
        {latest ? (
          <>
            <span className="font-medium text-foreground">{latest.title}</span>{" "}
            <span className="font-mono">{latest.id}</span>
            {" · "}
            {latest.n_test_cases} test cases
            {" · "}
            {latest.covered_requirements}/{latest.total_requirements} requirements covered
            {" · "}
            {latest.coverage_percent}%
          </>
        ) : (
          <span className="font-medium text-foreground">none</span>
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

export function UnsupportedActionNotice({ action }: { action: string }) {
  return (
    <div className="mt-3 p-2 border border-border rounded-md bg-muted text-muted-foreground text-xs">
      <div className="font-medium text-foreground">Action not available: {action}</div>
      <div className="mt-1">
        Chat can suggest changes, but persisted plan edits must go through the generation workflow.
      </div>
    </div>
  );
}

function PendingActionBanner({
  action,
  actionId,
  preview,
  onConfirm,
}: {
  action: string;
  actionId?: string | null;
  preview?: string | null;
  onConfirm: (confirmed: boolean, actionId?: string | null) => void;
}) {
  return (
    <div className="mt-3 p-2 border border-amber-300 rounded-md bg-amber-50 text-amber-900 text-xs">
      <div className="font-medium mb-2">Pending action: {action}</div>
      {preview && <div className="mb-2">{preview}</div>}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onConfirm(true, actionId)}>
          Confirm
        </Button>
        <Button size="sm" variant="outline" onClick={() => onConfirm(false, actionId)}>
          Discard
        </Button>
      </div>
    </div>
  );
}
