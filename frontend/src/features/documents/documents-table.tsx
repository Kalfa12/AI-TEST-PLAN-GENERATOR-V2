import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useDeleteDocument, useDocuments } from "./hooks";
import { getDocumentDownloadUrl } from "./api";
import { UploadDrawer } from "./upload-drawer";
import { formatDate } from "@/lib/utils";

export function DocumentsTable({ projectId }: { projectId: string }) {
  const { data: docs, isLoading } = useDocuments(projectId);
  const del = useDeleteDocument(projectId);
  const toast = useToast();
  const [open, setOpen] = useState(false);

  const onDelete = async (id: string, title: string) => {
    if (!confirm(`Delete "${title}" and all its derived requirements?`)) return;
    try {
      await del.mutateAsync(id);
      toast.push({ title: "Document deleted", tone: "success" });
    } catch (e) {
      toast.push({
        title: "Delete failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  const onDownload = (id: string) => {
    window.open(getDocumentDownloadUrl(projectId, id), "_blank", "noopener");
  };

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Documents</CardTitle>
        <Button onClick={() => setOpen(true)} size="sm">
          Upload
        </Button>
      </CardHeader>
      <CardBody className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : !docs || docs.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            No documents yet.
          </div>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Title</TH>
                <TH>Kind</TH>
                <TH>Scope</TH>
                <TH>Chunks</TH>
                <TH>Ingested</TH>
                <TH></TH>
              </TR>
            </THead>
            <TBody>
              {docs.map((d) => (
                <TR key={d.id}>
                  <TD className="font-medium">{d.title}</TD>
                  <TD>
                    <Badge tone="info">{d.kind}</Badge>
                  </TD>
                  <TD>
                    <Badge tone={d.scope === "general" ? "success" : "default"}>
                      {d.scope === "general" ? "General KB" : "Project"}
                    </Badge>
                  </TD>
                  <TD>{d.n_chunks}</TD>
                  <TD className="text-muted-foreground">
                    {formatDate(d.ingested_at)}
                  </TD>
                  <TD>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onDownload(d.id)}
                      >
                        Download
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onDelete(d.id, d.title)}
                        disabled={del.isPending}
                      >
                        Delete
                      </Button>
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardBody>
      <UploadDrawer
        projectId={projectId}
        open={open}
        onOpenChange={setOpen}
      />
    </Card>
  );
}
