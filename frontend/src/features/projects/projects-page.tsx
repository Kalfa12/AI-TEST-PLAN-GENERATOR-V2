import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useCreateProject, useDeleteProject, useProjects } from "./hooks";
import { formatDate } from "@/lib/utils";
import type { ProjectIndustry } from "@/lib/api/types";

const schema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().max(500).optional(),
  industry: z.enum(["generic", "aerospace", "automotive", "medical", "energy"]),
});

type FormValues = z.infer<typeof schema>;

const INDUSTRIES: Array<{ value: ProjectIndustry; label: string }> = [
  { value: "generic", label: "Generic" },
  { value: "aerospace", label: "Aerospace" },
  { value: "automotive", label: "Automotive" },
  { value: "medical", label: "Medical" },
  { value: "energy", label: "Energy" },
];

function industryLabel(industry: ProjectIndustry | undefined) {
  return INDUSTRIES.find((item) => item.value === industry)?.label ?? "Generic";
}

export function ProjectsPage() {
  const { data: projects, isLoading } = useProjects();
  const create = useCreateProject();
  const del = useDeleteProject();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { industry: "generic" },
  });

  const onSubmit = async (values: FormValues) => {
    await create.mutateAsync(values);
    setOpen(false);
    form.reset();
  };

  const onDeleteProject = async (projectId: string, name: string) => {
    if (
      !confirm(
        `Permanently delete "${name}"? This removes the project from the workspace and cannot be undone.`,
      )
    ) {
      return;
    }
    try {
      await del.mutateAsync(projectId);
      toast.push({ title: "Project deleted", tone: "success" });
    } catch (error) {
      toast.push({
        title: "Delete failed",
        description: (error as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Group documents and test plans together.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>New project</Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <Card key={p.id} className="h-full">
              <CardHeader>
                <CardTitle>{p.name}</CardTitle>
              </CardHeader>
              <CardBody className="space-y-4 text-sm text-muted-foreground">
                <div className="space-y-1">
                  {p.description && <p>{p.description}</p>}
                  <p className="text-xs">Industry: {industryLabel(p.industry)}</p>
                  <p className="text-xs">Created {formatDate(p.created_at)}</p>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onDeleteProject(p.id, p.name)}
                    disabled={del.isPending}
                  >
                    Delete
                  </Button>
                  <Link
                    to="/projects/$projectId"
                    params={{ projectId: p.id }}
                    className="inline-flex h-8 items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                  >
                    Open
                  </Link>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardBody className="text-sm text-muted-foreground">
            No projects yet. Click "New project" to create one.
          </CardBody>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <h2 className="text-lg font-semibold mb-4">New project</h2>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium">Name</label>
            <Input {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-xs text-destructive">
                {form.formState.errors.name.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Description</label>
            <Input {...form.register("description")} />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Industry</label>
            <select
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              {...form.register("industry")}
            >
              {INDUSTRIES.map((industry) => (
                <option key={industry.value} value={industry.value}>
                  {industry.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
