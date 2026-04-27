import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  useAddMember,
  useProjectMembers,
  useRemoveMember,
} from "./hooks";
import type { ProjectRole } from "./api";
import { formatDate } from "@/lib/utils";

const ROLES: ProjectRole[] = ["owner", "editor", "reviewer", "viewer"];

const roleTone = (role: string): "info" | "warning" | "success" | "default" => {
  if (role === "owner") return "warning";
  if (role === "editor") return "info";
  if (role === "reviewer") return "success";
  return "default";
};

export function MembersCard({ projectId }: { projectId: string }) {
  const { data: members, isLoading } = useProjectMembers(projectId);
  const add = useAddMember(projectId);
  const remove = useRemoveMember(projectId);
  const toast = useToast();
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<ProjectRole>("viewer");

  const onAdd = async () => {
    const trimmed = userId.trim();
    if (!trimmed) return;
    try {
      await add.mutateAsync({ user_id: trimmed, role });
      toast.push({ title: "Member added", tone: "success" });
      setUserId("");
      setRole("viewer");
    } catch (e) {
      toast.push({
        title: "Add failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onRemove = async (uid: string) => {
    if (!confirm(`Remove user ${uid} from this project?`)) return;
    try {
      await remove.mutateAsync(uid);
      toast.push({ title: "Member removed", tone: "success" });
    } catch (e) {
      toast.push({
        title: "Remove failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Team members</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* Add member form */}
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[200px] space-y-1">
            <label className="text-xs font-medium">User ID or email</label>
            <Input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="usr_abc123"
            />
          </div>
          <div className="space-y-1 w-36">
            <label className="text-xs font-medium">Role</label>
            <select
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value as ProjectRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={onAdd} disabled={!userId.trim() || add.isPending}>
            {add.isPending ? "Adding…" : "Add member"}
          </Button>
        </div>

        {/* Members table */}
        {isLoading ? (
          <Skeleton className="h-16" />
        ) : !members || members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No members yet. The project owner has full access by default.
          </p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>User</TH>
                <TH>Role</TH>
                <TH>Added</TH>
                <TH></TH>
              </TR>
            </THead>
            <TBody>
              {members.map((m) => (
                <TR key={m.user_id}>
                  <TD className="font-mono text-xs">{m.user_id}</TD>
                  <TD>
                    <Badge tone={roleTone(m.role)}>{m.role}</Badge>
                  </TD>
                  <TD className="text-muted-foreground text-xs">
                    {formatDate(m.added_at)}
                  </TD>
                  <TD>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onRemove(m.user_id)}
                      disabled={remove.isPending}
                    >
                      Remove
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}
