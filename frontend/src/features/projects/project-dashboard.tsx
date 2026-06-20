import { useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  useArchiveProject,
  useProject,
  useUpdateProject,
  useUpdateProjectBudget,
} from "./hooks";
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
  const updateBudget = useUpdateProjectBudget(projectId);
  const archive = useArchiveProject();
  const toast = useToast();

  const [editOpen, setEditOpen] = useState(false);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("");
  const [overrideBudget, setOverrideBudget] = useState("");
  const [overrideUntil, setOverrideUntil] = useState("");

  const openEdit = () => {
    setName(project.data?.name ?? "");
    setDescription(project.data?.description ?? "");
    setEditOpen(true);
  };

  const openBudget = () => {
    setMonthlyBudget(String(project.data?.monthly_budget_usd ?? 50));
    setOverrideBudget(
      project.data?.budget_override_usd != null
        ? String(project.data.budget_override_usd)
        : "",
    );
    setOverrideUntil(toDateTimeLocal(project.data?.budget_override_until));
    setBudgetOpen(true);
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

  const onSaveBudget = async () => {
    const parsedMonthly = Number(monthlyBudget);
    const parsedOverride = overrideBudget.trim() ? Number(overrideBudget) : null;
    const parsedOverrideUntil = overrideUntil.trim()
      ? new Date(overrideUntil).toISOString()
      : null;

    if (!Number.isFinite(parsedMonthly) || parsedMonthly < 0) {
      toast.push({ title: "Budget must be zero or higher", tone: "error" });
      return;
    }
    if (
      parsedOverride !== null &&
      (!Number.isFinite(parsedOverride) || parsedOverride < 0)
    ) {
      toast.push({ title: "Override must be zero or higher", tone: "error" });
      return;
    }
    if ((parsedOverride === null) !== (parsedOverrideUntil === null)) {
      toast.push({
        title: "Override amount and expiry must be set together",
        tone: "error",
      });
      return;
    }

    try {
      await updateBudget.mutateAsync({
        monthly_budget_usd: parsedMonthly,
        budget_override_usd: parsedOverride,
        budget_override_until: parsedOverrideUntil,
      });
      toast.push({ title: "Budget updated", tone: "success" });
      setBudgetOpen(false);
    } catch (e) {
      toast.push({
        title: "Budget update failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const spend = project.data?.current_month_spend_usd ?? 0;
  const effectiveBudget = getEffectiveBudget(project.data);
  const spendRatio =
    effectiveBudget > 0 ? Math.min((spend / effectiveBudget) * 100, 100) : 100;

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

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
            <CardTitle>LLM budget</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {project.isLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div>
                  <div className="text-2xl font-semibold">
                    {formatCurrency(spend)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    of {formatCurrency(effectiveBudget)} this month
                  </div>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary"
                    style={{ width: `${spendRatio}%` }}
                  />
                </div>
                {isOverrideActive(project.data) && (
                  <div className="text-xs text-muted-foreground">
                    Temporary override active until{" "}
                    {formatDate(project.data?.budget_override_until)}
                  </div>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  onClick={openBudget}
                >
                  Edit budget
                </Button>
              </>
            )}
          </CardBody>
        </Card>
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

      <Dialog open={budgetOpen} onOpenChange={setBudgetOpen}>
        <h2 className="text-lg font-semibold mb-4">LLM budget</h2>
        <div className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium">Monthly cap (USD)</label>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={monthlyBudget}
              onChange={(e) => setMonthlyBudget(e.target.value)}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium">Override cap (USD)</label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={overrideBudget}
                onChange={(e) => setOverrideBudget(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Override expiry</label>
              <Input
                type="datetime-local"
                value={overrideUntil}
                onChange={(e) => setOverrideUntil(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setBudgetOpen(false)}>
              Cancel
            </Button>
            <Button onClick={onSaveBudget} disabled={updateBudget.isPending}>
              {updateBudget.isPending ? "Saving…" : "Save"}
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

function formatCurrency(value: number | undefined | null) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value ?? 0);
}

function isOverrideActive(
  project:
    | {
        budget_override_usd?: number | null;
        budget_override_until?: string | null;
      }
    | undefined,
) {
  return Boolean(
    project?.budget_override_usd != null &&
      project.budget_override_until &&
      new Date(project.budget_override_until).getTime() >= Date.now(),
  );
}

function getEffectiveBudget(
  project:
    | {
        monthly_budget_usd?: number;
        budget_override_usd?: number | null;
        budget_override_until?: string | null;
      }
    | undefined,
) {
  if (isOverrideActive(project) && project?.budget_override_usd != null) {
    return project.budget_override_usd;
  }
  return project?.monthly_budget_usd ?? 0;
}

function toDateTimeLocal(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
