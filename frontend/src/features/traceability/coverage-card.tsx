import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getProjectCoverage, getProjectGaps } from "./api";

export function ProjectCoverageCard({ projectId }: { projectId: string }) {
  const coverage = useQuery({
    queryKey: ["project-coverage", projectId],
    queryFn: () => getProjectCoverage(projectId),
    enabled: !!projectId,
  });
  const gaps = useQuery({
    queryKey: ["project-gaps", projectId],
    queryFn: () => getProjectGaps(projectId),
    enabled: !!projectId,
  });

  const isLoading = coverage.isLoading || gaps.isLoading;
  const matrix = coverage.data ?? {};
  const total = Object.keys(matrix).length;
  const uncovered = gaps.data?.uncovered_requirement_ids ?? [];
  const covered = total - uncovered.length;
  const pct = total === 0 ? 0 : Math.round((covered / total) * 100);

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Requirement coverage</CardTitle>
        {!isLoading && total > 0 && (
          <Badge tone={pct === 100 ? "success" : pct >= 70 ? "info" : "warning"}>
            {pct}%
          </Badge>
        )}
      </CardHeader>
      <CardBody>
        {isLoading ? (
          <Skeleton className="h-24" />
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">
            No requirements extracted yet. Upload a specification document to get started.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="text-sm">
              <span className="font-medium">{covered}</span>
              <span className="text-muted-foreground"> / {total} requirements covered by at least one test case</span>
            </div>

            {/* Progress bar */}
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={
                  pct === 100
                    ? "h-full bg-emerald-500 transition-all"
                    : pct >= 70
                    ? "h-full bg-sky-500 transition-all"
                    : "h-full bg-amber-500 transition-all"
                }
                style={{ width: `${pct}%` }}
              />
            </div>

            {uncovered.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">
                  Uncovered ({uncovered.length})
                </div>
                <div className="flex flex-wrap gap-1 max-h-32 overflow-auto">
                  {uncovered.map((rid) => (
                    <Badge key={rid} tone="danger" className="font-mono">
                      {rid}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
