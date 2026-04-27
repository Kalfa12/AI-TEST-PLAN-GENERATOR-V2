import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/features/auth/hooks";
import { getCosts, listDeadLetter, requeueDeadLetter } from "./api";

export function AdminPage() {
  const { data: user } = useCurrentUser();
  if (!user) return null;
  if (!user.is_admin) {
    return (
      <div className="p-6">
        <Card>
          <CardBody className="text-sm text-muted-foreground">
            Admin access required.
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Admin</h1>
      <DeadLetterPanel />
      <CostsPanel />
    </div>
  );
}

function DeadLetterPanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const dl = useQuery({
    queryKey: ["admin", "dl"],
    queryFn: listDeadLetter,
  });
  const requeue = useMutation({
    mutationFn: (id: string) => requeueDeadLetter(id),
    onSuccess: () => {
      toast.push({ title: "Requeued", tone: "success" });
      qc.invalidateQueries({ queryKey: ["admin", "dl"] });
    },
    onError: (err) =>
      toast.push({
        title: "Requeue failed",
        description: (err as Error).message,
        tone: "error",
      }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Dead-letter jobs</CardTitle>
      </CardHeader>
      <CardBody className="p-0">
        {dl.isLoading ? (
          <div className="p-4 space-y-2">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : !dl.data || dl.data.items.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            Queue is clean.
          </div>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Job ID</TH>
                <TH>Task</TH>
                <TH>Failed at</TH>
                <TH>Error</TH>
                <TH></TH>
              </TR>
            </THead>
            <TBody>
              {dl.data.items.map((j) => (
                <TR key={j.job_id}>
                  <TD className="font-mono text-xs">{j.job_id}</TD>
                  <TD>{j.task_name}</TD>
                  <TD className="text-xs text-muted-foreground">{j.failed_at}</TD>
                  <TD className="text-xs max-w-md truncate" title={j.error}>
                    {j.error}
                  </TD>
                  <TD>
                    <Button
                      size="sm"
                      onClick={() => requeue.mutate(j.job_id)}
                      disabled={requeue.isPending}
                    >
                      Requeue
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}

function todayIso(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString();
}

function CostsPanel() {
  const [from, setFrom] = useState(() => todayIso(-7).slice(0, 10));
  const [to, setTo] = useState(() => todayIso(0).slice(0, 10));
  const [groupBy, setGroupBy] = useState<"project" | "user" | "model">("project");

  const costs = useQuery({
    queryKey: ["admin", "costs", from, to, groupBy],
    queryFn: () =>
      getCosts({
        from: `${from}T00:00:00Z`,
        to: `${to}T23:59:59Z`,
        group_by: groupBy,
      }),
  });

  useEffect(() => {
    costs.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to, groupBy]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>LLM costs</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <label className="text-xs">From</label>
            <Input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs">To</label>
            <Input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs">Group by</label>
            <select
              className="h-10 rounded-md border border-border bg-background px-3 text-sm"
              value={groupBy}
              onChange={(e) =>
                setGroupBy(e.target.value as "project" | "user" | "model")
              }
            >
              <option value="project">Project</option>
              <option value="user">User</option>
              <option value="model">Model</option>
            </select>
          </div>
        </div>
        {costs.isLoading ? (
          <Skeleton className="h-32" />
        ) : !costs.data || costs.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No cost rows for this range.</p>
        ) : (
          <Table>
            <THead>
              <TR>
                {Object.keys(costs.data[0]).map((k) => (
                  <TH key={k}>{k}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {costs.data.map((row, i) => (
                <TR key={i}>
                  {Object.values(row).map((v, j) => (
                    <TD key={j} className="text-xs">
                      {typeof v === "number" ? v.toFixed(4) : String(v)}
                    </TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}
