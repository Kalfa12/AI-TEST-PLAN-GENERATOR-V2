import { useMemo, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ChatListCard } from "@/features/chat/chat-list-card";
import { DocumentsTable } from "@/features/documents/documents-table";
import { useDocuments } from "@/features/documents/hooks";
import { PlansTable } from "@/features/plans/plans-table";
import { usePlans } from "@/features/plans/hooks";
import { RequirementsTable } from "@/features/requirements/requirements-table";
import { useRequirements } from "@/features/requirements/hooks";
import { ProjectCoverageCard } from "@/features/traceability/coverage-card";
import { formatDate } from "@/lib/utils";
import type { ProjectIndustry } from "@/lib/api/types";
import {
  useArchiveProject,
  useDeleteProject,
  useProject,
  useUpdateProject,
  useUpdateProjectBudget,
} from "./hooks";
import { MembersCard } from "./members-card";
import { ResourcesCard } from "./resources-card";

const INDUSTRIES: Array<{ value: ProjectIndustry; label: string }> = [
  { value: "generic", label: "Generic" },
  { value: "aerospace", label: "Aerospace" },
  { value: "automotive", label: "Automotive" },
  { value: "medical", label: "Medical" },
  { value: "energy", label: "Energy" },
];

const TABS = [
  "Overview",
  "Documents",
  "Requirements",
  "Plans",
  "Traceability",
  "Planning",
  "Collaboration",
  "Settings",
] as const;

type WorkspaceTab = (typeof TABS)[number];

function industryLabel(industry: ProjectIndustry | undefined) {
  return INDUSTRIES.find((item) => item.value === industry)?.label ?? "Generic";
}

export function ProjectDashboard() {
  const { projectId } = useParams({ strict: false }) as { projectId: string };
  const navigate = useNavigate();
  const project = useProject(projectId);
  const docs = useDocuments(projectId);
  const plans = usePlans(projectId);
  const requirements = useRequirements(projectId);
  const update = useUpdateProject(projectId);
  const updateBudget = useUpdateProjectBudget(projectId);
  const archive = useArchiveProject();
  const del = useDeleteProject();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<WorkspaceTab>("Overview");
  const [selectedRequirementIds, setSelectedRequirementIds] = useState<string[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [industry, setIndustry] = useState<ProjectIndustry>("generic");
  const [monthlyBudget, setMonthlyBudget] = useState("");
  const [overrideBudget, setOverrideBudget] = useState("");
  const [overrideUntil, setOverrideUntil] = useState("");

  const openEdit = () => {
    setName(project.data?.name ?? "");
    setDescription(project.data?.description ?? "");
    setIndustry(project.data?.industry ?? "generic");
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
      await update.mutateAsync({ name, description, industry });
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
    if (!confirm(`Archive "${project.data?.name ?? "this project"}"?`)) return;
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

  const onDelete = async () => {
    const projectName = project.data?.name ?? "this project";
    if (
      !confirm(
        `Permanently delete "${projectName}"? This removes the project and cannot be undone.`,
      )
    ) {
      return;
    }
    try {
      await del.mutateAsync(projectId);
      toast.push({ title: "Project deleted", tone: "success" });
      navigate({ to: "/projects" });
    } catch (e) {
      toast.push({
        title: "Delete failed",
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
  const coverageStats = useMemo(() => {
    const total = requirements.data?.length ?? 0;
    const plansCount = plans.data?.reduce((sum, plan) => sum + plan.n_test_cases, 0) ?? 0;
    return { total, plansCount };
  }, [plans.data, requirements.data]);

  return (
    <div className="min-h-screen bg-muted/20">
      <header className="border-b border-border bg-background">
        <div className="px-6 py-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone="default">{industryLabel(project.data?.industry)}</Badge>
                <span className="font-mono text-xs text-muted-foreground">{projectId}</span>
              </div>
              <h1 className="truncate text-2xl font-semibold tracking-normal">
                {project.data?.name ?? <Skeleton className="inline-block h-7 w-56" />}
              </h1>
              {project.data?.description && (
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  {project.data.description}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={openEdit}>
                Edit project
              </Button>
              <Button size="sm" variant="outline" onClick={openBudget}>
                LLM budget
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onArchive}
                disabled={archive.isPending}
              >
                Archive
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={onDelete}
                disabled={del.isPending}
              >
                Delete
              </Button>
            </div>
          </div>

          <div className="mt-5 overflow-x-auto">
            <div className="flex min-w-max gap-1 border-b border-border">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={
                    activeTab === tab
                      ? "border-b-2 border-primary px-3 py-2 text-sm font-medium text-foreground"
                      : "border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
                  }
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="space-y-5 p-6">
        {activeTab === "Overview" && (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                title="Documents"
                value={docs.data?.length ?? 0}
                loading={docs.isLoading}
              />
              <MetricCard
                title="Requirements"
                value={coverageStats.total}
                loading={requirements.isLoading}
              />
              <MetricCard
                title="Plans"
                value={plans.data?.length ?? 0}
                loading={plans.isLoading}
              />
              <MetricCard
                title="Test cases"
                value={coverageStats.plansCount}
                loading={plans.isLoading}
              />
            </div>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(340px,0.6fr)]">
              <ProjectCoverageCard projectId={projectId} />
              <BudgetPanel
                spend={spend}
                budget={effectiveBudget}
                ratio={spendRatio}
                overrideActive={isOverrideActive(project.data)}
                overrideUntil={project.data?.budget_override_until}
                onEdit={openBudget}
              />
            </div>
            <DocumentsTable projectId={projectId} />
          </>
        )}

        {activeTab === "Documents" && <DocumentsTable projectId={projectId} />}
        {activeTab === "Requirements" && (
          <RequirementsTable
            projectId={projectId}
            selectedRequirementIds={selectedRequirementIds}
            onSelectedRequirementIdsChange={setSelectedRequirementIds}
            onGenerateSelected={() => setActiveTab("Plans")}
          />
        )}
        {activeTab === "Plans" && (
          <PlansTable
            projectId={projectId}
            selectedRequirementIds={selectedRequirementIds}
            onClearSelectedRequirements={() => setSelectedRequirementIds([])}
          />
        )}
        {activeTab === "Traceability" && (
          <div className="space-y-5">
            <ProjectCoverageCard projectId={projectId} />
            <Card>
              <CardHeader className="flex items-center justify-between">
                <CardTitle>Trace graph</CardTitle>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate({ to: "/traceability" })}
                >
                  Open graph
                </Button>
              </CardHeader>
              <CardBody className="grid gap-4 md:grid-cols-3">
                <TraceMetric label="Extracted requirements" value={requirements.data?.length ?? 0} />
                <TraceMetric label="Generated plans" value={plans.data?.length ?? 0} />
                <TraceMetric label="Source documents" value={docs.data?.length ?? 0} />
              </CardBody>
            </Card>
          </div>
        )}
        {activeTab === "Planning" && <ResourcesCard projectId={projectId} />}
        {activeTab === "Collaboration" && (
          <div className="grid gap-5 xl:grid-cols-2">
            <ChatListCard projectId={projectId} />
            <MembersCard projectId={projectId} />
          </div>
        )}
        {activeTab === "Settings" && (
          <div className="grid gap-5 xl:grid-cols-2">
            <ProjectSettingsPanel
              projectName={project.data?.name}
              description={project.data?.description}
              industry={project.data?.industry}
              createdAt={project.data?.created_at}
              onEdit={openEdit}
            />
            <BudgetPanel
              spend={spend}
              budget={effectiveBudget}
              ratio={spendRatio}
              overrideActive={isOverrideActive(project.data)}
              overrideUntil={project.data?.budget_override_until}
              onEdit={openBudget}
            />
          </div>
        )}
      </main>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <h2 className="mb-4 text-lg font-semibold">Edit project</h2>
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
          <div className="space-y-1">
            <label className="text-sm font-medium">Industry</label>
            <select
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              value={industry}
              onChange={(e) => setIndustry(e.target.value as ProjectIndustry)}
            >
              {INDUSTRIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={update.isPending || !name.trim()}>
              {update.isPending ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={budgetOpen} onOpenChange={setBudgetOpen}>
        <h2 className="mb-4 text-lg font-semibold">LLM budget</h2>
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
              {updateBudget.isPending ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

function MetricCard({
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
        <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardBody>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <div className="text-3xl font-semibold">{value}</div>
        )}
      </CardBody>
    </Card>
  );
}

function BudgetPanel({
  spend,
  budget,
  ratio,
  overrideActive,
  overrideUntil,
  onEdit,
}: {
  spend: number;
  budget: number;
  ratio: number;
  overrideActive: boolean;
  overrideUntil?: string | null;
  onEdit: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>LLM budget</CardTitle>
        <Button size="sm" variant="outline" type="button" onClick={onEdit}>
          Edit
        </Button>
      </CardHeader>
      <CardBody className="space-y-3">
        <div>
          <div className="text-2xl font-semibold">{formatCurrency(spend)}</div>
          <div className="text-xs text-muted-foreground">
            of {formatCurrency(budget)} this month
          </div>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-primary" style={{ width: `${ratio}%` }} />
        </div>
        {overrideActive && (
          <div className="text-xs text-muted-foreground">
            Override until {formatDate(overrideUntil)}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ProjectSettingsPanel({
  projectName,
  description,
  industry,
  createdAt,
  onEdit,
}: {
  projectName?: string;
  description?: string | null;
  industry?: ProjectIndustry;
  createdAt?: string;
  onEdit: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Project settings</CardTitle>
        <Button size="sm" variant="outline" type="button" onClick={onEdit}>
          Edit
        </Button>
      </CardHeader>
      <CardBody className="divide-y divide-border p-0 text-sm">
        <SettingRow label="Name" value={projectName ?? ""} />
        <SettingRow label="Description" value={description || ""} />
        <SettingRow label="Industry" value={industryLabel(industry)} />
        <SettingRow label="Created" value={formatDate(createdAt)} />
      </CardBody>
    </Card>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-4 px-4 py-3">
      <div className="text-muted-foreground">{label}</div>
      <div className="min-w-0 truncate font-medium">{value || "-"}</div>
    </div>
  );
}

function TraceMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
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
  return (
    [
      date.getFullYear(),
      pad(date.getMonth() + 1),
      pad(date.getDate()),
    ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
