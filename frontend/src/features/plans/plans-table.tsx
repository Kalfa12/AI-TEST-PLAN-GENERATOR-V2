import { useState, useCallback } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
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
  goal: z.string().min(1, "Goal is required"),
  detail_level: z.enum(["summary", "detailed"]).default("detailed"),
  interactive: z.boolean().default(false),
});

type FormValues = z.infer<typeof schema>;

interface ActiveJob {
  jobId: string;
  sessionId: string;
}

export function PlansTable({ projectId }: { projectId: string }) {
  const { data: plans, isLoading } = usePlans(projectId);
  const requirements = useRequirements(projectId);
  const create = useCreatePlan(projectId);
  const del = useDeletePlan(projectId);
  const toast = useToast();
  const navigate = useNavigate();
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
    defaultValues: { goal: "", detail_level: "detailed", interactive: false },
  });

  const handleJobDone = useCallback((_planId: string | null) => {
    setActiveJob(null);
  }, []);

  const { status: jobStatus, error: jobError } = usePlanJobPolling(
    activeJob?.jobId ?? null,
    handleJobDone,
  );

  const onSubmit = async (values: FormValues) => {
    try {
      const r = await create.mutateAsync(values);
      setOpen(false);
      form.reset();
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
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Extracted requirements</div>
              <div className="mt-1 text-xl font-semibold">
                {requirements.isLoading ? "..." : requirements.data?.length ?? 0}
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
              placeholder="e.g. Validate API authentication for v2 release"
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
              disabled={create.isPending || (requirements.data?.length ?? 0) === 0}
            >
              {create.isPending ? "Starting…" : "Generate"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
