import { useMemo, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import {
  useGenerateRequirementTestCase,
  usePlan,
  usePlanCoverage,
  useSchedulePlan,
  useUpdateTestCaseStatus,
} from "./hooks";
import { exportPlanJson } from "./api";
import { exportPlanToPdf } from "./pdf-export";
import { useToast } from "@/components/ui/toast";
import { usePlanDefects } from "@/features/quality/hooks";
import { DefectsPanel } from "@/features/quality/defects-panel";
import { useResources } from "@/features/projects/hooks";
import type {
  Resource,
  SourceEvidence,
  TestCaseStatus,
  TestCaseSummary,
  TestSchedule,
} from "@/lib/api/types";

export function PlanDetailPage() {
  const { projectId, planId } = useParams({ strict: false }) as {
    projectId: string;
    planId: string;
  };
  const summary = usePlan(projectId, planId, "summary");
  const full = usePlan(projectId, planId, "full");
  const coverage = usePlanCoverage(projectId, planId);
  const defects = usePlanDefects(projectId, planId);
  const resources = useResources(projectId);
  const schedule = useSchedulePlan(projectId, planId);
  const updateStatus = useUpdateTestCaseStatus(projectId, planId);
  const generateRequirementTest = useGenerateRequirementTestCase(projectId, planId);
  const toast = useToast();

  const [detail, setDetail] = useState<"summary" | "full">("full");
  const plan = detail === "full" ? full.data : summary.data;
  const isLoading = full.isLoading && summary.isLoading;
  const testCaseCount = plan?.n_test_cases ?? plan?.test_cases.length ?? 0;
  const versionLabel = plan?.version
    ? plan.version.startsWith("v")
      ? plan.version
      : `v${plan.version}`
    : null;

  const onExportJson = async () => {
    if (!plan) return;
    try {
      const blob = await exportPlanJson(projectId, planId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${plan.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.push({
        title: "Export failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onExportPdf = () => {
    if (!plan) return;
    try {
      exportPlanToPdf(plan, coverage.data?.matrix);
    } catch (e) {
      toast.push({
        title: "PDF export failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onRefreshSchedule = async () => {
    try {
      await schedule.mutateAsync();
      toast.push({ title: "Schedule updated", tone: "success" });
    } catch (e) {
      toast.push({
        title: "Schedule failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onGenerateRequirementTest = async (requirementId: string) => {
    try {
      const reply = await generateRequirementTest.mutateAsync(requirementId);
      toast.push({
        title: "Test case generated",
        description: reply.test_case.title,
        tone: "success",
      });
    } catch (e) {
      toast.push({
        title: "Generation failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  if (isLoading || !plan) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{plan.title}</h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
              <span>{testCaseCount} test case{testCaseCount === 1 ? "" : "s"}</span>
              {versionLabel && <span className="font-mono">{versionLabel}</span>}
              {plan.author && <span>by {plan.author}</span>}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Tabs value={detail} onValueChange={(v) => setDetail(v as "summary" | "full")}>
              <TabsList>
                <TabsTrigger value="summary">Résumé</TabsTrigger>
                <TabsTrigger value="full">Détaillé</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="outline" size="sm" onClick={onExportJson}>
              Export JSON
            </Button>
            <Button size="sm" onClick={onExportPdf}>
              Export PDF
            </Button>
          </div>
        </div>

        {/* Introduction */}
        {plan.introduction && (
          <Card>
            <CardHeader><CardTitle>Introduction</CardTitle></CardHeader>
            <CardBody className="text-sm whitespace-pre-wrap">{plan.introduction}</CardBody>
          </Card>
        )}

        {/* Objectives */}
        {plan.objectives && plan.objectives.length > 0 && (
          <Card>
            <CardHeader><CardTitle>Objectives</CardTitle></CardHeader>
            <CardBody className="text-sm">
              <ul className="list-disc ml-5 space-y-0.5">
                {plan.objectives.map((o, i) => <li key={i}>{o}</li>)}
              </ul>
            </CardBody>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Strategy card */}
          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>Strategy</CardTitle></CardHeader>
            <CardBody className="space-y-3 text-sm">
              <div>
                <div className="text-xs uppercase text-muted-foreground">Scope</div>
                <p>{plan.scope || "—"}</p>
              </div>
              {plan.out_of_scope && plan.out_of_scope.length > 0 && (
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Out of scope</div>
                  <ul className="list-disc ml-5">
                    {plan.out_of_scope.map((o, i) => <li key={i}>{o}</li>)}
                  </ul>
                </div>
              )}
              <div>
                <div className="text-xs uppercase text-muted-foreground">Strategy</div>
                <p>{plan.strategy || "—"}</p>
              </div>
              {plan.entry_criteria && plan.entry_criteria.length > 0 && (
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Entry criteria</div>
                  <ul className="list-disc ml-5">
                    {plan.entry_criteria.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
              {plan.exit_criteria && plan.exit_criteria.length > 0 && (
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Exit criteria</div>
                  <ul className="list-disc ml-5">
                    {plan.exit_criteria.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </div>
              )}
              {plan.risks && plan.risks.length > 0 && (
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Risks</div>
                  <ul className="list-disc ml-5">
                    {plan.risks.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Coverage card */}
          <Card>
            <CardHeader><CardTitle>Coverage</CardTitle></CardHeader>
            <CardBody>
              {coverage.isLoading ? (
                <Skeleton className="h-24" />
              ) : !coverage.data || Object.keys(coverage.data.matrix).length === 0 ? (
                <p className="text-sm text-muted-foreground">No coverage data available.</p>
              ) : (
                <CoverageList
                  matrix={coverage.data.matrix}
                  onGenerate={onGenerateRequirementTest}
                  generatingRequirementId={
                    generateRequirementTest.isPending
                      ? generateRequirementTest.variables
                      : null
                  }
                />
              )}
            </CardBody>
          </Card>
        </div>

        {/* Quality / defect report */}
        {defects.data && <DefectsPanel report={defects.data} />}

        <ScheduleCard
          schedule={full.data?.schedule ?? null}
          resources={resources.data ?? []}
          onRefresh={onRefreshSchedule}
          refreshing={schedule.isPending}
        />

        {/* Test cases */}
        <Card>
          <CardHeader><CardTitle>Test cases</CardTitle></CardHeader>
          <CardBody className="p-0">
            <TestCaseTable
              cases={plan.test_cases}
              detail={detail}
              onStatusChange={async (testCaseId, status) => {
                try {
                  await updateStatus.mutateAsync({ testCaseId, status });
                  toast.push({ title: "Status updated", tone: "success" });
                } catch (e) {
                  toast.push({
                    title: "Status update failed",
                    description: (e as Error).message,
                    tone: "error",
                  });
                }
              }}
            />
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function CoverageList({
  matrix,
  onGenerate,
  generatingRequirementId,
}: {
  matrix: Record<string, string[]>;
  onGenerate: (requirementId: string) => Promise<void>;
  generatingRequirementId?: string | null;
}) {
  const stats = useMemo(() => {
    const total = Object.keys(matrix).length;
    const covered = Object.values(matrix).filter((v) => v.length > 0).length;
    return { total, covered, pct: total === 0 ? 0 : Math.round((covered / total) * 100) };
  }, [matrix]);
  return (
    <div className="space-y-3">
      <div className="text-sm">
        {stats.covered}/{stats.total} requirements covered ({stats.pct}%)
      </div>
      <ul className="space-y-1 text-sm max-h-72 overflow-auto">
        {Object.entries(matrix).map(([req, tcs]) => (
          <li key={req} className="flex items-center justify-between gap-2">
            <span className="font-mono text-xs">{req}</span>
            <div className="flex items-center gap-2">
              <Badge tone={tcs.length > 0 ? "success" : "danger"}>
                {tcs.length} TC
              </Badge>
              {tcs.length === 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onGenerate(req)}
                  disabled={generatingRequirementId !== null && generatingRequirementId !== undefined}
                >
                  {generatingRequirementId === req ? "Generating..." : "Generate test"}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScheduleCard({
  schedule,
  resources,
  onRefresh,
  refreshing,
}: {
  schedule: TestSchedule | null;
  resources: Resource[];
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const resourceById = useMemo(
    () => Object.fromEntries(resources.map((resource) => [resource.id, resource])),
    [resources],
  );
  const assignments = Object.entries(schedule?.assignments ?? {});

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Schedule</CardTitle>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onRefresh}
          disabled={refreshing}
        >
          {refreshing ? "Scheduling..." : "Refresh schedule"}
        </Button>
      </CardHeader>
      <CardBody className="p-0">
        {assignments.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            No assignments yet.
          </p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Test case</TH>
                <TH>Start</TH>
                <TH>End</TH>
                <TH>Resources</TH>
                <TH>Service</TH>
              </TR>
            </THead>
            <TBody>
              {assignments.map(([testCaseId, assignment]) => (
                <TR key={testCaseId}>
                  <TD className="font-mono text-xs">{testCaseId}</TD>
                  <TD>{assignment.start}</TD>
                  <TD>{assignment.end}</TD>
                  <TD>
                    {assignment.resource_ids
                      .map((id) => resourceById[id]?.name ?? id)
                      .join(", ") || "—"}
                  </TD>
                  <TD className="text-muted-foreground">{assignment.service ?? "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}

const STATUS_OPTIONS: TestCaseStatus[] = [
  "not_started",
  "planned",
  "running",
  "blocked",
  "passed",
  "failed",
];

function statusLabel(status: TestCaseStatus | undefined) {
  return (status ?? "not_started").replaceAll("_", " ");
}

function TestCaseTable({
  cases,
  detail,
  onStatusChange,
}: {
  cases: TestCaseSummary[];
  detail: "summary" | "full";
  onStatusChange: (testCaseId: string, status: TestCaseStatus) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  if (cases.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">No test cases.</div>;
  }

  const riskLabel = (level: number) => {
    if (level >= 4) return "Critical";
    if (level >= 3) return "High";
    if (level >= 2) return "Medium";
    return "Low";
  };

  return (
    <Table>
      <THead>
        <TR>
          <TH>Title</TH>
          <TH>Risk</TH>
          <TH>Requirements</TH>
          <TH>Duration</TH>
          <TH>Status</TH>
          <TH>Assignee</TH>
        </TR>
      </THead>
      <TBody>
        {cases.map((tc) => {
          const open = expanded[tc.id] ?? false;
          return (
            <>
              <TR
                key={tc.id}
                onClick={() => setExpanded((e) => ({ ...e, [tc.id]: !open }))}
                className="cursor-pointer"
              >
                <TD className="font-medium">{tc.title}</TD>
                <TD>
                  <Badge tone={tc.risk_level >= 3 ? "danger" : tc.risk_level === 2 ? "warning" : "info"}>
                    {riskLabel(tc.risk_level)}
                  </Badge>
                </TD>
                <TD className="text-xs font-mono">
                  {tc.requirement_ids.join(", ") || "—"}
                </TD>
                <TD className="text-muted-foreground">
                  {tc.estimated_duration_minutes ? `${tc.estimated_duration_minutes} min` : "—"}
                </TD>
                <TD onClick={(e) => e.stopPropagation()}>
                  <select
                    className="h-8 rounded-md border border-border bg-background px-2 text-sm capitalize"
                    value={tc.status ?? "not_started"}
                    onChange={(e) =>
                      onStatusChange(tc.id, e.target.value as TestCaseStatus)
                    }
                  >
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {statusLabel(status)}
                      </option>
                    ))}
                  </select>
                </TD>
                <TD className="text-muted-foreground">{tc.assignee ?? "—"}</TD>
              </TR>
              {open && (
                <TR key={`${tc.id}-d`}>
                  <TD colSpan={6} className="bg-muted/30">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-2 text-sm">
                      {/* Objective */}
                      <div className="md:col-span-2">
                        <div className="text-xs uppercase text-muted-foreground mb-0.5">Objective</div>
                        <p>{tc.objective}</p>
                      </div>

                      {/* Risk description */}
                      {tc.risk_description && (
                        <div className="md:col-span-2">
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Risk description</div>
                          <p>{tc.risk_description}</p>
                        </div>
                      )}

                      {tc.source_evidence && tc.source_evidence.length > 0 && (
                        <div className="md:col-span-2">
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Source evidence</div>
                          <SourceEvidenceList evidence={tc.source_evidence} />
                        </div>
                      )}

                      {/* Testing types */}
                      {tc.testing_types && tc.testing_types.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Testing types</div>
                          <div className="flex flex-wrap gap-1">
                            {tc.testing_types.map((t, i) => (
                              <Badge key={i} tone="info">{t}</Badge>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Features not tested */}
                      {tc.features_not_tested && tc.features_not_tested.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Features not tested</div>
                          <ul className="list-disc ml-4">
                            {tc.features_not_tested.map((f, i) => <li key={i}>{f}</li>)}
                          </ul>
                        </div>
                      )}

                      {/* Deliverables */}
                      {tc.deliverables && tc.deliverables.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Deliverables</div>
                          <ul className="list-disc ml-4">
                            {tc.deliverables.map((d, i) => <li key={i}>{d}</li>)}
                          </ul>
                        </div>
                      )}

                      {/* Dependencies */}
                      {tc.dependencies && tc.dependencies.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Dependencies</div>
                          <ul className="list-disc ml-4">
                            {tc.dependencies.map((d, i) => <li key={i}>{d}</li>)}
                          </ul>
                        </div>
                      )}

                      {/* KPIs */}
                      {tc.kpis && tc.kpis.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">KPIs</div>
                          <ul className="list-disc ml-4">
                            {tc.kpis.map((k, i) => <li key={i}>{k}</li>)}
                          </ul>
                        </div>
                      )}

                      {/* Steps */}
                      {detail === "full" && tc.steps && tc.steps.length > 0 && (
                        <div className="md:col-span-2">
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Steps</div>
                          <ol className="list-decimal ml-5 space-y-1">
                            {tc.steps.map((s) => (
                              <li key={s.id}>
                                <div>
                                  <span className="font-medium">{s.action}</span>
                                </div>
                                <div className="text-muted-foreground">
                                  Expected: {s.expected_result}
                                </div>
                                {s.notes && (
                                  <div className="text-xs text-muted-foreground italic">
                                    {s.notes}
                                  </div>
                                )}
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {/* Acceptance criteria */}
                      {detail === "full" && tc.acceptance_criteria && tc.acceptance_criteria.length > 0 && (
                        <div className="md:col-span-2">
                          <div className="text-xs uppercase text-muted-foreground mb-0.5">Acceptance criteria</div>
                          <ul className="list-disc ml-5 space-y-1">
                            {tc.acceptance_criteria.map((c) => (
                              <li key={c.id}>
                                <span>{c.statement}</span>
                                {c.tolerance && (
                                  <span className="ml-2 font-mono text-xs text-muted-foreground">
                                    ({c.tolerance})
                                  </span>
                                )}
                                {!c.measurable && (
                                  <Badge tone="default" className="ml-2">qualitative</Badge>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </TD>
                </TR>
              )}
            </>
          );
        })}
      </TBody>
    </Table>
  );
}

export function SourceEvidenceList({
  evidence,
}: {
  evidence: SourceEvidence[];
}) {
  return (
    <ul className="space-y-2">
      {evidence.map((ev, i) => (
        <li
          key={`${ev.chunk_id}-${i}`}
          className="rounded border border-border bg-background px-3 py-2"
        >
          <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-muted-foreground">
            <span>{ev.relation}</span>
            <span>{ev.document_id}</span>
            <span>{ev.chunk_id}</span>
            {ev.page_start && (
              <span>
                p.{ev.page_start}
                {ev.page_end && ev.page_end !== ev.page_start ? `-${ev.page_end}` : ""}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap">
            {ev.excerpt}
          </p>
        </li>
      ))}
    </ul>
  );
}
