import { useNavigate, useParams } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useProject } from "./hooks";
import { useDocuments } from "@/features/documents/hooks";
import { usePlans } from "@/features/plans/hooks";
import { DocumentsTable } from "@/features/documents/documents-table";
import { PlansTable } from "@/features/plans/plans-table";
import { formatDate } from "@/lib/utils";

export function ProjectDashboard() {
  const { projectId } = useParams({ strict: false }) as { projectId: string };
  const navigate = useNavigate();
  const project = useProject(projectId);
  const docs = useDocuments(projectId);
  const plans = usePlans(projectId);

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
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              navigate({
                to: "/chat/$sessionId",
                params: { sessionId: `proj-${projectId}` },
              })
            }
          >
            Open copilot
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

      <DocumentsTable projectId={projectId} />
      <PlansTable projectId={projectId} />
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
