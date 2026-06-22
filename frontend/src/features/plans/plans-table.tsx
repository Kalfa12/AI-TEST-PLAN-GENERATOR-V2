import { useState, useCallback, useEffect, useMemo } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useCreatePlan, useDeletePlan, usePlans, usePlanJobPolling } from "./hooks";
import { AgentProgress } from "./agent-progress";
import { useRequirements } from "@/features/requirements/hooks";

const schema = z.object({
  goal: z.string().default(""),
  detail_level: z.enum(["summary", "detailed"]).default("detailed"),
  requirement_mode: z.enum(["all", "selected", "reextract"]).default("all"),
  interactive: z.boolean().default(false),
});

type FormValues = z.infer<typeof schema>;

interface ActiveJob {
  jobId: string;
  sessionId: string;
}

interface PlansTableProps {
  projectId: string;
  selectedRequirementIds?: string[];
  onClearSelectedRequirements?: () => void;
}

export function PlansTable({
  projectId,
  selectedRequirementIds = [],
  onClearSelectedRequirements,
}: PlansTableProps) {
  const { data: plans, isLoading } = usePlans(projectId);
  const requirements = useRequirements(projectId);
  const create = useCreatePlan(projectId);
  const del = useDeletePlan(projectId);
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null);

  const onDelete = async (id: string, title: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Delete plan "${title}"? This cannot be undone.`)) return;
    try {
      await del.mutateAsync(id);
      toast.push({ title: "Plan deleted", tone: "success" });
    } catch (err) {
      toast.push({
        title: "Delete failed",
        description: (err as Error).message,
        tone: "error",
      });
    }
  };
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      goal: "",
      detail_level: "detailed",
      requirement_mode: "all",
      interactive: false,
    },
  });
  const requirementMode = form.watch("requirement_mode");

  useEffect(() => {
    if (open && selectedRequirementIds.length > 0) {
      form.setValue("requirement_mode", "selected");
    } else if (open && selectedRequirementIds.length === 0) {
      form.setValue("requirement_mode", "all");
    }
  }, [form, open, selectedRequirementIds.length]);

  const selectedRequirementPreview = useMemo(() => {
    const byId = new Map((requirements.data ?? []).map((req) => [req.id, req]));
    return selectedRequirementIds
      .slice(0, 5)
      .map((id) => byId.get(id)?.external_id ?? byId.get(id)?.id ?? id);
  }, [requirements.data, selectedRequirementIds]);

  const handleJobDone = useCallback((planId: string | null) => {
    setActiveJob(null);
    queryClient.invalidateQueries({ queryKey: ["plans", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-coverage", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-gaps", projectId] });
    queryClient.invalidateQueries({ queryKey: ["chat-context", projectId] });
    if (planId) {
      queryClient.invalidateQueries({ queryKey: ["plan", projectId, planId] });
      queryClient.invalidateQueries({ queryKey: ["plan-coverage", projectId, planId] });
      queryClient.invalidateQueries({ queryKey: ["plan-defects", projectId, planId] });
    }
  }, [projectId, queryClient]);

  const { status: jobStatus, error: jobError } = usePlanJobPolling(
    activeJob?.jobId ?? null,
    handleJobDone,
  );

  const onSubmit = async (values: FormValues) => {
    try {
      const r = await create.mutateAsync({
        ...values,
        goal:
          values.goal.trim() ||
          "Generate a complete test plan from the current project requirements.",
        requirement_ids:
          values.requirement_mode === "selected" ? selectedRequirementIds : [],
      });
      setOpen(false);
      form.reset({
        goal: "",
        detail_level: "detailed",
        requirement_mode: selectedRequirementIds.length > 0 ? "selected" : "all",
        interactive: false,
      });
      if (values.requirement_mode === "selected") {
        onClearSelectedRequirements?.();
      }
      if (values.interactive) {
        // Interactive runs go straight to the workspace where the user
        // can accept / reprompt at each checkpoint.
        navigate({
          to: "/projects/$projectId/runs/$jobId",
          params: { projectId, jobId: r.job_id },
        });
        return;
      }
      setActiveJob({ jobId: r.job_id, sessionId: r.session_id });
      toast.push({
        title: "Plan generation started",
        description: "Agents are working on your plan…",
        tone: "info",
      });
    } catch (e) {
      toast.push({
        title: "Failed to start plan",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <>
      {activeJob && (
        <AgentProgress
          sessionId={activeJob.sessionId}
          jobStatus={jobStatus}
          jobError={jobError}
        />
      )}

      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Plans</CardTitle>
          <Button size="sm" onClick={() => setOpen(true)} disabled={!!activeJob}>
            {activeJob ? "Generating…" : "Generate plan"}
          </Button>
        </CardHeader>
        <CardBody className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-2">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : !plans || plans.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground text-center">
              No plans yet.
            </div>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH>Detail</TH>
                  <TH>Test cases</TH>
                  <TH></TH>
                </TR>
              </THead>
              <TBody>
                {plans.map((p) => (
                  <TR key={p.id}>
                    <TD className="font-medium">{p.title}</TD>
                    <TD>
                      <Badge tone="info">{p.detail_level}</Badge>
                    </TD>
                    <TD>{p.n_test_cases}</TD>
                    <TD>
                      <div className="flex items-center gap-3">
                        <Link
                          to="/projects/$projectId/plans/$planId"
                          params={{ projectId, planId: p.id }}
                          className="text-sm underline"
                        >
                          Open
                        </Link>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => onDelete(p.id, p.title, e)}
                          disabled={del.isPending}
                        >
                          Delete
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <h2 className="text-lg font-semibold mb-4">Generate plan</h2>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Extracted requirements</div>
              <div className="mt-1 text-xl font-semibold">
                {requirements.isLoading ? "..." : requirements.data?.length ?? 0}
              </div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Selected</div>
              <div className="mt-1 text-xl font-semibold">
                {selectedRequirementIds.length}
              </div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Existing plans</div>
              <div className="mt-1 text-xl font-semibold">{plans?.length ?? 0}</div>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Goal</label>
            <Input
              placeholder="Optional focus, e.g. validate API authentication for v2 release"
              {...form.register("goal")}
            />
            {form.formState.errors.goal && (
              <p className="text-xs text-destructive">
                {form.formState.errors.goal.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Detail level</label>
            <select
              className="flex h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              {...form.register("detail_level")}
            >
              <option value="detailed">Detailed</option>
              <option value="summary">Summary</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Requirement basis</label>
            <div className="grid gap-2">
              <RequirementModeOption
                value="all"
                current={requirementMode}
                title="All extracted requirements"
                description={`${requirements.data?.length ?? 0} stored project requirements will be sent to the agents.`}
                onChange={() => form.setValue("requirement_mode", "all")}
              />
              <RequirementModeOption
                value="selected"
                current={requirementMode}
                title="Selected requirements"
                description={
                  selectedRequirementIds.length > 0
                    ? `${selectedRequirementIds.length} selected: ${selectedRequirementPreview.join(", ")}`
                    : "Select requirements in the Requirements tab first."
                }
                disabled={selectedRequirementIds.length === 0}
                onChange={() => form.setValue("requirement_mode", "selected")}
              />
              <RequirementModeOption
                value="reextract"
                current={requirementMode}
                title="Re-extract from source documents"
                description="Run the extractor again before architecture and test generation."
                onChange={() => form.setValue("requirement_mode", "reextract")}
              />
            </div>
          </div>
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5"
                {...form.register("interactive")}
              />
              <div className="flex-1">
                <div className="text-sm font-medium">Interactive mode</div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Pause after each major step (requirements, strategy, test cases)
                  so you can accept the output or send the agent feedback before continuing.
                  Recommended for high-stakes plans.
                </p>
              </div>
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                create.isPending ||
                (requirementMode === "all" &&
                  !requirements.isLoading &&
                  (requirements.data?.length ?? 0) === 0) ||
                (requirementMode === "selected" && selectedRequirementIds.length === 0)
              }
            >
              {create.isPending ? "Starting…" : "Generate"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

function RequirementModeOption({
  value,
  current,
  title,
  description,
  disabled,
  onChange,
}: {
  value: FormValues["requirement_mode"];
  current: FormValues["requirement_mode"];
  title: string;
  description: string;
  disabled?: boolean;
  onChange: () => void;
}) {
  const active = value === current;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onChange}
      className={
        active
          ? "rounded-md border border-primary bg-primary/5 p-3 text-left"
          : "rounded-md border border-border bg-background p-3 text-left hover:bg-muted/40 disabled:cursor-not-allowed disabled:opacity-50"
      }
    >
      <div className="flex items-start gap-2">
        <span
          className={
            active
              ? "mt-0.5 h-3 w-3 rounded-full border border-primary bg-primary"
              : "mt-0.5 h-3 w-3 rounded-full border border-muted-foreground"
          }
        />
        <span className="min-w-0">
          <span className="block text-sm font-medium">{title}</span>
          <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
            {description}
          </span>
        </span>
      </div>
    </button>
  );
}
