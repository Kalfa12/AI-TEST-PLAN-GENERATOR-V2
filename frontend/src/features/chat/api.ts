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

export async function confirmAction(
  sessionId: string,
  confirmed: boolean,
): Promise<ChatReply> {
  const res = await http.post<ChatReply>(`/chat/${sessionId}/confirm`, {
    confirmed,
  });
  return res.data;
}

export interface StreamingMessage {
  onToken: (t: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}

export function openChatStream(sessionId: string): WebSocket {
  const tokens = readTokens();
  const params = new URLSearchParams();
  if (tokens) params.set("token", tokens.access);
  // Note: backend WS does not currently parse the token query param;
  // it is included for forward compatibility with token-aware proxies.
  const url = `${wsBaseURL}/chat/${encodeURIComponent(sessionId)}/stream${
    params.toString() ? `?${params}` : ""
  }`;
  return new WebSocket(url);
}
