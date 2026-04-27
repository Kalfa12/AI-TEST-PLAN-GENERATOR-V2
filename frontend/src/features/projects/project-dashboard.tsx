import { useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useArchiveProject, useProject, useUpdateProject } from "./hooks";
import { useDocuments } from "@/features/documents/hooks";
import { usePlans } from "@/features/plans/hooks";
import { DocumentsTable } from "@/features/documents/documents-table";
import { PlansTable } from "@/features/plans/plans-table";
import { MembersCard } from "./members-card";
import { ProjectCoverageCard } from "@/features/traceability/coverage-card";
import { ChatListCard } from "@/features/chat/chat-list-card";
import { formatDate } from "@/lib/utils";

export function ProjectDashboard() {
  const { projectId } = useParams({ strict: false }) as { projectId: string };
  const navigate = useNavigate();
  const project = useProject(projectId);
  const docs = useDocuments(projectId);
  const plans = usePlans(projectId);
  const update = useUpdateProject(projectId);
  const archive = useArchiveProject();
  const toast = useToast();

  const [editOpen, setEditOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const openEdit = () => {
    setName(project.data?.name ?? "");
    setDescription(project.data?.description ?? "");
    setEditOpen(true);
  };

  const onSave = async () => {
    try {
      await update.mutateAsync({ name, description });
      toast.push({ title: "Project updated", tone: "success" });
      setEditOpen(false);
    } catch (e) {
      toast.push({
        title: "Update failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onArchive = async () => {
    if (!confirm(`Archive "${project.data?.name ?? "this project"}"? It will no longer appear in your project list.`)) return;
    try {
      await archive.mutateAsync(projectId);
      toast.push({ title: "Project archived", tone: "success" });
      navigate({ to: "/projects" });
    } catch (e) {
      toast.push({
        title: "Archive failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            {project.data?.name ?? <Skeleton className="h-7 w-48 inline-block" />}
          </h1>
          {project.data?.description && (
            <p className="text-sm text-muted-foreground mt-1">
              {project.data.description}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={openEdit}>
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onArchive}
            disabled={archive.isPending}
          >
            Archive
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard
          title="Documents"
          value={docs.data?.length ?? 0}
          loading={docs.isLoading}
        />
        <SummaryCard
          title="Plans"
          value={plans.data?.length ?? 0}
          loading={plans.isLoading}
        />
        <Card>
          <CardHeader>
            <CardTitle>Last activity</CardTitle>
          </CardHeader>
          <CardBody className="text-sm text-muted-foreground">
            {project.isLoading ? (
              <Skeleton className="h-5 w-32" />
            ) : (
              formatDate(project.data?.created_at)
            )}
          </CardBody>
        </Card>
      </div>

      <ProjectCoverageCard projectId={projectId} />
      <DocumentsTable projectId={projectId} />
      <PlansTable projectId={projectId} />
      <ChatListCard projectId={projectId} />
      <MembersCard projectId={projectId} />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <h2 className="text-lg font-semibold mb-4">Edit project</h2>
        <div className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Description</label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={update.isPending || !name.trim()}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  loading,
}: {
  title: string;
  value: number;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        {loading ? (
          <Skeleton className="h-8 w-12" />
        ) : (
          <div className="text-3xl font-semibold">{value}</div>
        )}
      </CardBody>
    </Card>
  );
}
