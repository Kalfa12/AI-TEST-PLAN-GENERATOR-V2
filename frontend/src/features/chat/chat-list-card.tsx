import { useEffect, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChatSession,
  createSession,
  deleteSession as deleteLocalSession,
  listSessionsForProject,
} from "@/lib/chat-sessions";

export function ChatListCard({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  const refresh = () => setSessions(listSessionsForProject(projectId));

  useEffect(() => {
    refresh();
  }, [projectId]);

  const onNewChat = () => {
    const s = createSession(projectId);
    navigate({ to: "/chat/$sessionId", params: { sessionId: s.id } });
  };

  const onDelete = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this chat session from your local history?")) return;
    deleteLocalSession(id);
    refresh();
  };

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Copilot conversations</CardTitle>
        <Button size="sm" onClick={onNewChat}>
          New chat
        </Button>
      </CardHeader>
      <CardBody>
        {sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No conversations yet. Start a new chat with the project copilot.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {sessions.map((s) => (
              <li key={s.id}>
                <Link
                  to="/chat/$sessionId"
                  params={{ sessionId: s.id }}
                  className="block py-2 px-2 -mx-2 hover:bg-accent/40 rounded"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{s.title}</div>
                      <div className="text-xs text-muted-foreground font-mono truncate">
                        {s.id}
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(s.updatedAt).toLocaleString()}
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => onDelete(s.id, e)}
                    >
                      ×
                    </Button>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
