import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useDocuments } from "./hooks";
import { UploadDrawer } from "./upload-drawer";
import { formatDate } from "@/lib/utils";

export function DocumentsTable({ projectId }: { projectId: string }) {
  const { data: docs, isLoading } = useDocuments(projectId);
  const [open, setOpen] = useState(false);

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
                <TH>Chunks</TH>
                <TH>Ingested</TH>
              </TR>
            </THead>
            <TBody>
              {docs.map((d) => (
                <TR key={d.id}>
                  <TD className="font-medium">{d.title}</TD>
                  <TD>
                    <Badge tone="info">{d.kind}</Badge>
                  </TD>
                  <TD>{d.n_chunks}</TD>
                  <TD className="text-muted-foreground">
                    {formatDate(d.ingested_at)}
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
