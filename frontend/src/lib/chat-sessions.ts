/**
 * Per-project chat session registry.
 *
 * The backend persists chat events keyed by session_id but has no list-sessions
 * endpoint. We keep the registry client-side in localStorage so users can
 * resume past conversations and switch between them.
 */

const STORAGE_KEY = "chat-sessions:v1";

export interface ChatSession {
  id: string;
  projectId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

function readAll(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(sessions: ChatSession[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function listSessionsForProject(projectId: string): ChatSession[] {
  return readAll()
    .filter((s) => s.projectId === projectId)
    .sort((a, b) => (a.updatedAt > b.updatedAt ? -1 : 1));
}

export function getSession(sessionId: string): ChatSession | null {
  return readAll().find((s) => s.id === sessionId) ?? null;
}

export function makeSessionId(projectId: string): string {
  const slug = projectId.replace(/[^a-zA-Z0-9]/g, "").slice(0, 10);
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 6);
  return `sess_${slug}_${ts}${rand}`;
}

export function createSession(projectId: string, title = "New chat"): ChatSession {
  const now = new Date().toISOString();
  const session: ChatSession = {
    id: makeSessionId(projectId),
    projectId,
    title,
    createdAt: now,
    updatedAt: now,
  };
  const all = readAll();
  all.push(session);
  writeAll(all);
  return session;
}

export function touchSession(sessionId: string, title?: string): void {
  const all = readAll();
  const s = all.find((x) => x.id === sessionId);
  if (!s) return;
  s.updatedAt = new Date().toISOString();
  if (title && (s.title === "New chat" || !s.title)) {
    s.title = title.slice(0, 80);
  }
  writeAll(all);
}

export function deleteSession(sessionId: string): void {
  writeAll(readAll().filter((s) => s.id !== sessionId));
}

export function renameSession(sessionId: string, title: string): void {
  const all = readAll();
  const s = all.find((x) => x.id === sessionId);
  if (!s) return;
  s.title = title.slice(0, 80);
  s.updatedAt = new Date().toISOString();
  writeAll(all);
}
