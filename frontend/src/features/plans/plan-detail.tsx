import { useMemo, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { usePlan, usePlanCoverage } from "./hooks";
import type { TestCaseSummary } from "@/lib/api/types";

export function PlanDetailPage() {
  const { projectId, planId } = useParams({ strict: false }) as {
    projectId: string;
    planId: string;
  };
  // Both detail levels are pre-fetched into the React Query cache so flipping
  // the tab is < 200 ms (no network round-trip).
  const summary = usePlan(projectId, planId, "summary");
  const full = usePlan(projectId, planId, "full");
  const coverage = usePlanCoverage(projectId, planId);

  const [detail, setDetail] = useState<"summary" | "full">("full");
  const plan = detail === "full" ? full.data : summary.data;
  const isLoading = full.isLoading && summary.isLoading;

  const onExportJson = () => {
    if (!plan) return;
    const blob = new Blob([JSON.stringify(plan, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${plan.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
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
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{plan.title}</h1>
          <p className="text-sm text-muted-foreground">
            {plan.n_test_cases} test case{plan.n_test_cases === 1 ? "" : "s"}
          </p>
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
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            Print / PDF
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Strategy</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3 text-sm">
            <div>
              <div className="text-xs uppercase text-muted-foreground">Scope</div>
              <p>{plan.scope || "—"}</p>
            </div>
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
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Coverage</CardTitle>
          </CardHeader>
          <CardBody>
            {coverage.isLoading ? (
              <Skeleton className="h-24" />
            ) : !coverage.data ||
              Object.keys(coverage.data.matrix).length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No coverage data available.
              </p>
            ) : (
              <CoverageList matrix={coverage.data.matrix} />
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Test cases</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          <TestCaseTable cases={plan.test_cases} detail={detail} />
        </CardBody>
      </Card>
    </div>
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
  return (
    <Table>
      <THead>
        <TR>
          <TH>Title</TH>
          <TH>Risk</TH>
          <TH>Requirements</TH>
          <TH>Duration</TH>
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
                  <Badge
                    tone={
                      tc.risk_level >= 3 ? "danger" : tc.risk_level === 2 ? "warning" : "info"
                    }
                  >
                    {tc.risk_level}
                  </Badge>
                </TD>
                <TD className="text-xs font-mono">
                  {tc.requirement_ids.join(", ") || "—"}
                </TD>
                <TD className="text-muted-foreground">
                  {tc.estimated_duration_minutes
                    ? `${tc.estimated_duration_minutes} min`
                    : "—"}
                </TD>
              </TR>
              {open && (
                <TR key={`${tc.id}-d`}>
                  <TD colSpan={4} className="bg-muted/30">
                    <div className="space-y-2 text-sm">
                      <p>{tc.objective}</p>
                      {detail === "full" && tc.steps && tc.steps.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">
                            Steps
                          </div>
                          <ol className="list-decimal ml-5">
                            {tc.steps.map((s, i) => <li key={i}>{s}</li>)}
                          </ol>
                        </div>
                      )}
                      {detail === "full" && tc.acceptance_criteria && tc.acceptance_criteria.length > 0 && (
                        <div>
                          <div className="text-xs uppercase text-muted-foreground">
                            Acceptance criteria
                          </div>
                          <ul className="list-disc ml-5">
                            {tc.acceptance_criteria.map((c, i) => <li key={i}>{c}</li>)}
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
