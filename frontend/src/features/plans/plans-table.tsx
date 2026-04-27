import { useState } from "react";
import { Link } from "@tanstack/react-router";
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
import { useCreatePlan, usePlans } from "./hooks";

const schema = z.object({
  goal: z.string().min(1, "Goal is required"),
  detail_level: z.enum(["summary", "detailed"]).default("detailed"),
});

type FormValues = z.infer<typeof schema>;

export function PlansTable({ projectId }: { projectId: string }) {
  const { data: plans, isLoading } = usePlans(projectId);
  const create = useCreatePlan(projectId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { goal: "", detail_level: "detailed" },
  });

  const onSubmit = async (values: FormValues) => {
    try {
      const r = await create.mutateAsync(values);
      toast.push({
        title: "Plan generation started",
        description: `Job ${r.job_id}`,
        tone: "info",
      });
      setOpen(false);
      form.reset();
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
      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Plans</CardTitle>
          <Button size="sm" onClick={() => setOpen(true)}>
            Generate plan
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
                      <Link
                        to="/projects/$projectId/plans/$planId"
                        params={{ projectId, planId: p.id }}
                        className="text-sm underline"
                      >
                        Open
                      </Link>
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
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Starting…" : "Generate"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
