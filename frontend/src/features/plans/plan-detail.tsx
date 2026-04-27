import { useMemo, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { usePlan, usePlanCoverage } from "./hooks";
import { exportPlanJson } from "./api";
import { exportPlanToPdf } from "./pdf-export";
import { useToast } from "@/components/ui/toast";
import type { TestCaseSummary } from "@/lib/api/types";

export function PlanDetailPage() {
  const { projectId, planId } = useParams({ strict: false }) as {
    projectId: string;
    planId: string;
  };
  const summary = usePlan(projectId, planId, "summary");
  const full = usePlan(projectId, planId, "full");
  const coverage = usePlanCoverage(projectId, planId);
  const toast = useToast();

  const [detail, setDetail] = useState<"summary" | "full">("full");
  const plan = detail === "full" ? full.data : summary.data;
  const isLoading = full.isLoading && summary.isLoading;

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
              <span>{plan.n_test_cases} test case{plan.n_test_cases === 1 ? "" : "s"}</span>
              {plan.version && <span className="font-mono">v{plan.version}</span>}
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
                <CoverageList matrix={coverage.data.matrix} />
              )}
            </CardBody>
          </Card>
        </div>

        {/* Test cases */}
        <Card>
          <CardHeader><CardTitle>Test cases</CardTitle></CardHeader>
          <CardBody className="p-0">
            <TestCaseTable cases={plan.test_cases} detail={detail} />
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function CoverageList({ matrix }: { matrix: Record<string, string[]> }) {
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
            <Badge tone={tcs.length > 0 ? "success" : "danger"}>
              {tcs.length} TC
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TestCaseTable({
  cases,
  detail,
}: {
  cases: TestCaseSummary[];
  detail: "summary" | "full";
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
                <TD className="text-muted-foreground">{tc.assignee ?? "—"}</TD>
              </TR>
              {open && (
                <TR key={`${tc.id}-d`}>
                  <TD colSpan={5} className="bg-muted/30">
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
