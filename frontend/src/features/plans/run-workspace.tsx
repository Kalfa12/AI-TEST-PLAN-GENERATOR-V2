import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { getCheckpoint, getJobStatus, resumeJob } from "./api";
import { AgentProgress } from "./agent-progress";
import type { CheckpointResponse, JobStatus } from "@/lib/api/types";

const CHECKPOINT_LABELS: Record<string, string> = {
  extractor: "Requirements extraction",
  architect: "Test plan strategy",
  generator: "Test cases",
};

const CHECKPOINT_DESCRIPTIONS: Record<string, string> = {
  extractor:
    "The extractor agent has parsed the project documents and proposed the requirements below. Review them, then either accept or send feedback to refine.",
  architect:
    "The architect agent has drafted the plan's strategy, scope, and entry/exit criteria. Approve to continue to test case generation, or reprompt for changes.",
  generator:
    "The generator agent has written one or more test cases per requirement. Approve to finalise, or send feedback to regenerate.",
};

export function RunWorkspacePage() {
  const { projectId, jobId } = useParams({ strict: false }) as {
    projectId: string;
    jobId: string;
  };
  const navigate = useNavigate();
  const toast = useToast();

  const [job, setJob] = useState<JobStatus | null>(null);
  const [checkpoint, setCheckpoint] = useState<CheckpointResponse | null>(null);
  const [polling, setPolling] = useState(true);
  const [actionPending, setActionPending] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const j = await getJobStatus(jobId);
      setJob(j);
      if (j.status === "paused" && j.paused_at) {
        try {
          const cp = await getCheckpoint(jobId);
          setCheckpoint(cp);
        } catch {
          // Race: status flipped between calls. Will catch next tick.
        }
      } else {
        setCheckpoint(null);
      }
      if (j.status === "succeeded" || j.status === "failed") {
        setPolling(false);
      }
    } catch (e) {
      toast.push({
        title: "Job poll failed",
        description: (e as Error).message,
        tone: "error",
      });
      setPolling(false);
    }
  }, [jobId, toast]);

  useEffect(() => {
    if (!polling) return;
    refresh();
    const id = setInterval(refresh, 2_000);
    return () => clearInterval(id);
  }, [polling, refresh]);

  const onAccept = async () => {
    setActionPending(true);
    try {
      await resumeJob(jobId, { action: "accept" });
      setCheckpoint(null);
      await refresh();
    } catch (e) {
      toast.push({
        title: "Resume failed",
        description: (e as Error).message,
        tone: "error",
      });
    } finally {
      setActionPending(false);
    }
  };

  const onReprompt = async (feedback: string) => {
    if (!feedback.trim()) return;
    setActionPending(true);
    try {
      await resumeJob(jobId, { action: "reprompt", feedback });
      setCheckpoint(null);
      await refresh();
    } catch (e) {
      toast.push({
        title: "Resume failed",
        description: (e as Error).message,
        tone: "error",
      });
    } finally {
      setActionPending(false);
    }
  };

  const onAbort = async () => {
    if (!confirm("Abort this run? The plan will not be saved.")) return;
    try {
      await resumeJob(jobId, { action: "abort" });
      navigate({ to: "/projects/$projectId", params: { projectId } });
    } catch (e) {
      toast.push({
        title: "Abort failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onOpenPlan = () => {
    const planId = (job?.result?.plan_id as string | undefined) ?? null;
    if (!planId) return;
    navigate({
      to: "/projects/$projectId/plans/$planId",
      params: { projectId, planId },
    });
  };

  const sessionId = (job?.session_id ?? null) as string | null;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Plan generation workspace</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Interactive mode — review each agent's output and steer the run.
          </p>
          <p className="text-xs text-muted-foreground font-mono mt-1">
            Job: {jobId}
          </p>
        </div>
        <div className="flex gap-2">
          {job?.status === "succeeded" && Boolean(job.result?.plan_id) && (
            <Button onClick={onOpenPlan}>Open plan</Button>
          )}
          {job?.status !== "succeeded" && job?.status !== "failed" && (
            <Button variant="outline" onClick={onAbort}>
              Abort
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() =>
              navigate({ to: "/projects/$projectId", params: { projectId } })
            }
          >
            Back to project
          </Button>
        </div>
      </div>

      {/* Live agent progress */}
      <AgentProgress
        sessionId={sessionId}
        jobStatus={job?.status ?? null}
        jobError={job?.error ?? null}
      />

      {/* Checkpoint card */}
      {checkpoint ? (
        <CheckpointCard
          checkpoint={checkpoint}
          actionPending={actionPending}
          onAccept={onAccept}
          onReprompt={onReprompt}
          onAbort={onAbort}
        />
      ) : job?.status === "paused" ? (
        <Card>
          <CardBody className="text-sm text-muted-foreground">
            <Skeleton className="h-32" />
          </CardBody>
        </Card>
      ) : null}

      {/* Done banner */}
      {job?.status === "succeeded" && (
        <Card className="border-emerald-300 bg-emerald-50">
          <CardBody className="text-sm text-emerald-900">
            ✓ Plan generation complete.
            {job.result?.n_test_cases !== undefined && (
              <span> {String(job.result.n_test_cases)} test cases were created.</span>
            )}
          </CardBody>
        </Card>
      )}
      {job?.status === "failed" && (
        <Card className="border-red-300 bg-red-50">
          <CardBody className="text-sm text-red-900">
            ✗ Run failed: {job.error ?? "unknown error"}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// Build a free-text feedback draft from the partial defect report so the
// user doesn't have to retype what the static checks already flagged.
function draftFeedbackFromDefects(
  checkpoint: CheckpointResponse,
): string {
  const targetKind =
    checkpoint.paused_at === "extractor"
      ? "requirement"
      : checkpoint.paused_at === "generator"
      ? "test_case"
      : null;
  if (!targetKind) return "";

  const report = checkpoint.state.defect_report as
    | { defects?: Array<Record<string, unknown>> }
    | null
    | undefined;
  const defects = report?.defects ?? [];
  if (defects.length === 0) return "";

  const SEVERITY_RANK_LOCAL: Record<string, number> = {
    critical: 3,
    major: 2,
    minor: 1,
  };

  const relevant = defects
    .filter((d) => d.target_kind === targetKind)
    .sort(
      (a, b) =>
        (SEVERITY_RANK_LOCAL[String(b.severity)] ?? 0) -
        (SEVERITY_RANK_LOCAL[String(a.severity)] ?? 0),
    )
    .slice(0, 8);

  if (relevant.length === 0) return "";

  const lines = relevant.map((d) => {
    const id = String(d.target_id ?? "?");
    const type = String(d.defect_type ?? "defect").replace(/_/g, " ");
    const evidence = String(d.evidence ?? "");
    const fix = d.suggestion ? ` Fix: ${String(d.suggestion)}` : "";
    return `- ${id} (${type}): ${evidence}${fix}`;
  });
  return `Address the following defects:\n${lines.join("\n")}`;
}

export function CheckpointCard({
  checkpoint,
  actionPending,
  onAccept,
  onReprompt,
  onAbort,
}: {
  checkpoint: CheckpointResponse;
  actionPending: boolean;
  onAccept: () => void;
  onReprompt: (feedback: string) => void;
  onAbort?: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  // Reset whenever a new checkpoint arrives.
  useEffect(() => {
    setFeedback("");
    setShowFeedback(false);
  }, [checkpoint.paused_at]);

  // Open feedback panel pre-filled with the defect summary the agent
  // detected, so the engineer can trim/edit instead of typing from scratch.
  const onOpenFeedbackFromDefects = () => {
    const draft = draftFeedbackFromDefects(checkpoint);
    setFeedback(draft);
    setShowFeedback(true);
  };

  const defectDraftAvailable = draftFeedbackFromDefects(checkpoint).length > 0;

  const previousFeedback =
    (checkpoint.state.user_feedback?.[checkpoint.paused_at] as string[] | undefined) ?? [];

  return (
    <Card className="border-amber-300 bg-amber-50/30">
      <CardHeader className="flex items-center justify-between">
        <div>
          <CardTitle>
            Checkpoint: {CHECKPOINT_LABELS[checkpoint.paused_at] ?? checkpoint.paused_at}
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            {CHECKPOINT_DESCRIPTIONS[checkpoint.paused_at]}
          </p>
        </div>
        <Badge tone="warning">Awaiting your review</Badge>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* Output preview */}
        <div className="rounded border border-border bg-background p-3 max-h-96 overflow-auto">
          {checkpoint.paused_at === "extractor" && (
            <RequirementsPreview state={checkpoint.state} />
          )}
          {checkpoint.paused_at === "architect" && (
            <ArchitectPreview state={checkpoint.state} />
          )}
          {checkpoint.paused_at === "generator" && (
            <GeneratorPreview state={checkpoint.state} />
          )}
        </div>

        {/* Previous feedback */}
        {previousFeedback.length > 0 && (
          <div className="rounded border border-border p-3 text-xs">
            <div className="uppercase text-muted-foreground mb-1">
              Feedback you sent earlier ({previousFeedback.length})
            </div>
            <ul className="list-disc ml-5 space-y-0.5">
              {previousFeedback.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Controls */}
        {!showFeedback ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={onAccept} disabled={actionPending}>
              {actionPending ? "Working…" : "Accept and continue"}
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowFeedback(true)}
              disabled={actionPending}
            >
              Send feedback and re-run
            </Button>
            {defectDraftAvailable && (
              <Button
                variant="outline"
                onClick={onOpenFeedbackFromDefects}
                disabled={actionPending}
              >
                Reprompt from detected defects
              </Button>
            )}
            {onAbort && (
              <Button
                variant="outline"
                onClick={onAbort}
                disabled={actionPending}
              >
                Abort run
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Tell the agent what to change
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="e.g. Focus on cybersecurity edge cases, use IEC 61508 SIL-2 wording, drop the regression suite…"
              className="w-full min-h-[100px] rounded-md border border-border bg-background px-3 py-2 text-sm"
              autoFocus
            />
            <div className="flex gap-2">
              <Button
                onClick={() => onReprompt(feedback)}
                disabled={actionPending || !feedback.trim()}
              >
                {actionPending ? "Re-running…" : "Send feedback"}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setShowFeedback(false);
                  setFeedback("");
                }}
                disabled={actionPending}
              >
                Cancel
              </Button>
              {onAbort && (
                <Button
                  variant="outline"
                  onClick={onAbort}
                  disabled={actionPending}
                >
                  Abort run
                </Button>
              )}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// ---- per-checkpoint preview components ----

type DefectMap = Map<
  string,
  { count: number; worst: "critical" | "major" | "minor" }
>;

const SEVERITY_RANK = { critical: 3, major: 2, minor: 1 } as const;

function defectsByTarget(state: Record<string, unknown>): DefectMap {
  const out: DefectMap = new Map();
  const report = state.defect_report as
    | { defects?: Array<Record<string, unknown>> }
    | null
    | undefined;
  if (!report?.defects) return out;
  for (const d of report.defects) {
    const id = String(d.target_id ?? "");
    if (!id) continue;
    const sev = (d.severity as "critical" | "major" | "minor") ?? "minor";
    const prev = out.get(id);
    if (!prev) {
      out.set(id, { count: 1, worst: sev });
    } else {
      prev.count += 1;
      if (SEVERITY_RANK[sev] > SEVERITY_RANK[prev.worst]) prev.worst = sev;
    }
  }
  return out;
}

function DefectDot({
  entry,
}: {
  entry: { count: number; worst: "critical" | "major" | "minor" } | undefined;
}) {
  if (!entry) return null;
  const tone =
    entry.worst === "critical"
      ? "danger"
      : entry.worst === "major"
      ? "warning"
      : "info";
  return (
    <Badge tone={tone} title={`${entry.count} defect(s), worst: ${entry.worst}`}>
      {entry.count} defect{entry.count > 1 ? "s" : ""}
    </Badge>
  );
}

function RequirementsPreview({ state }: { state: Record<string, unknown> }) {
  const reqs = (state.requirements ?? []) as Array<Record<string, unknown>>;
  const defects = defectsByTarget(state);
  if (reqs.length === 0) {
    return <p className="text-sm text-muted-foreground">No requirements extracted.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{reqs.length} requirements</div>
      <ul className="space-y-2 text-sm">
        {reqs.slice(0, 50).map((r, i) => (
          <li key={(r.id as string) ?? i} className="border-b border-border pb-2 last:border-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs">{String(r.id ?? `req-${i}`)}</span>
              <Badge tone="info">{String(r.kind ?? "?")}</Badge>
              <span className="text-xs text-muted-foreground">
                priority {String(r.priority ?? "—")}
              </span>
              <DefectDot entry={defects.get(String(r.id ?? ""))} />
            </div>
            <div className="font-medium mt-0.5">{String(r.title ?? "")}</div>
            <div className="text-xs text-muted-foreground">
              {String(r.statement ?? "")}
            </div>
          </li>
        ))}
        {reqs.length > 50 && (
          <li className="text-xs text-muted-foreground italic">
            (+{reqs.length - 50} more not shown — accept to use all of them)
          </li>
        )}
      </ul>
    </div>
  );
}

function ArchitectPreview({ state }: { state: Record<string, unknown> }) {
  const plan = (state.plan ?? {}) as Record<string, unknown>;
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-xs uppercase text-muted-foreground">Title</div>
        <div className="font-medium">{String(plan.title ?? "—")}</div>
      </div>
      {plan.introduction ? (
        <Section label="Introduction" body={String(plan.introduction)} />
      ) : null}
      {Array.isArray(plan.objectives) && plan.objectives.length > 0 && (
        <BulletSection label="Objectives" items={plan.objectives as string[]} />
      )}
      <Section label="Scope" body={String(plan.scope ?? "—")} />
      {Array.isArray(plan.out_of_scope) && plan.out_of_scope.length > 0 && (
        <BulletSection label="Out of scope" items={plan.out_of_scope as string[]} />
      )}
      <Section label="Strategy" body={String(plan.strategy ?? "—")} />
      {Array.isArray(plan.entry_criteria) && plan.entry_criteria.length > 0 && (
        <BulletSection label="Entry criteria" items={plan.entry_criteria as string[]} />
      )}
      {Array.isArray(plan.exit_criteria) && plan.exit_criteria.length > 0 && (
        <BulletSection label="Exit criteria" items={plan.exit_criteria as string[]} />
      )}
      {Array.isArray(plan.risks) && plan.risks.length > 0 && (
        <BulletSection label="Risks" items={plan.risks as string[]} />
      )}
    </div>
  );
}

function GeneratorPreview({ state }: { state: Record<string, unknown> }) {
  const tcs = (state.test_cases ?? []) as Array<Record<string, unknown>>;
  const defects = defectsByTarget(state);
  if (tcs.length === 0) {
    return <p className="text-sm text-muted-foreground">No test cases generated.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{tcs.length} test cases</div>
      <ul className="space-y-2 text-sm">
        {tcs.map((tc, i) => (
          <li key={(tc.id as string) ?? i} className="border-b border-border pb-2 last:border-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs">TC-{String(i + 1).padStart(3, "0")}</span>
              <Badge
                tone={
                  Number(tc.risk_level) >= 3
                    ? "danger"
                    : Number(tc.risk_level) === 2
                    ? "warning"
                    : "info"
                }
              >
                risk {String(tc.risk_level ?? "—")}
              </Badge>
              {Array.isArray(tc.requirement_ids) && (
                <span className="text-xs font-mono text-muted-foreground">
                  {(tc.requirement_ids as string[]).join(", ")}
                </span>
              )}
              <DefectDot entry={defects.get(String(tc.id ?? ""))} />
            </div>
            <div className="font-medium mt-0.5">{String(tc.title ?? "")}</div>
            <div className="text-xs text-muted-foreground">
              {String(tc.objective ?? "")}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Section({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <p className="whitespace-pre-wrap">{body}</p>
    </div>
  );
}

function BulletSection({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <ul className="list-disc ml-5">
        {items.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}
