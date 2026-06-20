import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  useCreateResource,
  useDeleteResource,
  useResources,
} from "./hooks";

export function ResourcesCard({ projectId }: { projectId: string }) {
  const resources = useResources(projectId);
  const create = useCreateResource(projectId);
  const remove = useDeleteResource(projectId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [service, setService] = useState("");
  const [role, setRole] = useState("");
  const [availability, setAvailability] = useState("100");

  const reset = () => {
    setName("");
    setService("");
    setRole("");
    setAvailability("100");
  };

  const onCreate = async () => {
    const availability_pct = Number(availability);
    if (!name.trim() || !service.trim()) return;
    if (!Number.isFinite(availability_pct) || availability_pct < 0 || availability_pct > 100) {
      toast.push({ title: "Availability must be between 0 and 100", tone: "error" });
      return;
    }
    try {
      await create.mutateAsync({
        name,
        service,
        role: role.trim() || null,
        availability_pct,
      });
      toast.push({ title: "Resource created", tone: "success" });
      reset();
      setOpen(false);
    } catch (e) {
      toast.push({
        title: "Resource creation failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this planning resource?")) return;
    try {
      await remove.mutateAsync(id);
      toast.push({ title: "Resource deleted", tone: "success" });
    } catch (e) {
      toast.push({
        title: "Delete failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Planning resources</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)}>
          Add resource
        </Button>
      </CardHeader>
      <CardBody className="p-0">
        {resources.isLoading ? (
          <div className="p-6"><Skeleton className="h-16" /></div>
        ) : !resources.data || resources.data.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            No resources configured.
          </p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Service</TH>
                <TH>Role</TH>
                <TH>Availability</TH>
                <TH></TH>
              </TR>
            </THead>
            <TBody>
              {resources.data.map((resource) => (
                <TR key={resource.id}>
                  <TD className="font-medium">{resource.name}</TD>
                  <TD>{resource.service}</TD>
                  <TD className="text-muted-foreground">{resource.role ?? "—"}</TD>
                  <TD>{resource.availability_pct}%</TD>
                  <TD className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onDelete(resource.id)}
                      disabled={remove.isPending}
                    >
                      Delete
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>

      <Dialog open={open} onOpenChange={setOpen}>
        <h2 className="text-lg font-semibold mb-4">Add resource</h2>
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium">Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Service</label>
              <Input value={service} onChange={(e) => setService(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium">Role</label>
              <Input value={role} onChange={(e) => setRole(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Availability (%)</label>
              <Input
                type="number"
                min="0"
                max="100"
                value={availability}
                onChange={(e) => setAvailability(e.target.value)}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={onCreate}
              disabled={create.isPending || !name.trim() || !service.trim()}
            >
              {create.isPending ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </Dialog>
    </Card>
  );
}
