import { http, wsBaseURL } from "@/lib/api/http";
import { readTokens } from "@/lib/auth/storage";
import type { ChatReply } from "@/lib/api/types";

export async function sendChat(body: {
  session_id?: string;
  project_id?: string;
  message: string;
}): Promise<ChatReply> {
  const res = await http.post<ChatReply>("/chat", body);
  return res.data;
}

export interface ChatHistoryEvent {
  ts: string;
  actor: string;
  kind: string;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface ChatHistoryResponse {
  session_id: string;
  events: ChatHistoryEvent[];
}

export async function getChatHistory(
  sessionId: string,
  limit = 50,
): Promise<ChatHistoryResponse> {
  const res = await http.get<ChatHistoryResponse>(
    `/chat/${encodeURIComponent(sessionId)}/history`,
    { params: { limit } },
  );
  return res.data;
}

export async function confirmAction(
  sessionId: string,
  confirmed: boolean,
  actionId?: string | null,
): Promise<ChatReply> {
  const res = await http.post<ChatReply>(`/chat/${sessionId}/confirm`, {
    confirmed,
    action_id: actionId,
  });
  return res.data;
}

export interface StreamingMessage {
  onToken: (t: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}

export function openChatStream(sessionId: string, projectId?: string): WebSocket {
  const tokens = readTokens();
  const params = new URLSearchParams();
  if (tokens) params.set("token", tokens.access);
  if (projectId) params.set("project_id", projectId);
  const url = `${wsBaseURL}/chat/${encodeURIComponent(sessionId)}/stream${
    params.toString() ? `?${params}` : ""
  }`;
  return new WebSocket(url);
}
