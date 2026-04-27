import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Drawer } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  useDeleteGeneralDocument,
  useGeneralDocuments,
  useJobPolling,
  useUploadGeneralDocument,
} from "./hooks";
import { formatBytes, formatDate } from "@/lib/utils";

export function KnowledgePage() {
  const { data: docs, isLoading } = useGeneralDocuments();
  const del = useDeleteGeneralDocument();
  const toast = useToast();
  const [open, setOpen] = useState(false);

  const onDelete = async (id: string, title: string) => {
    if (!confirm(`Delete "${title}" from the general knowledge base?`)) return;
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

  const totalChunks = docs?.reduce((acc, d) => acc + d.n_chunks, 0) ?? 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">General Knowledge Base</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Cross-project documents the agents can pull from when generating any plan
            (standards, glossaries, regulatory texts, organisational guidelines).
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          Upload to KB
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard title="Documents" value={docs?.length ?? 0} loading={isLoading} />
        <SummaryCard title="Indexed chunks" value={totalChunks} loading={isLoading} />
        <Card>
          <CardHeader><CardTitle>Scope</CardTitle></CardHeader>
          <CardBody>
            <Badge tone="success">General KB</Badge>
            <p className="text-xs text-muted-foreground mt-2">
              Available to all projects
            </p>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Documents in the knowledge base</CardTitle></CardHeader>
        <CardBody className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-2">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : !docs || docs.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground text-center">
              No general knowledge yet. Upload a document to make it available to all projects.
            </div>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Title</TH>
                  <TH>Kind</TH>
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
                    <TD>{d.n_chunks}</TD>
                    <TD className="text-muted-foreground">{formatDate(d.ingested_at)}</TD>
                    <TD>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onDelete(d.id, d.title)}
                        disabled={del.isPending}
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
      </Card>

      <KnowledgeUploadDrawer open={open} onOpenChange={setOpen} />
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
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
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

function KnowledgeUploadDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const upload = useUploadGeneralDocument();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJobPolling(jobId);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setProgress(0);
      setJobId(null);
    }
  }, [open]);

  useEffect(() => {
    if (!jobId) return;
    if (job.status === "succeeded") {
      toast.push({ title: "Knowledge ingested", tone: "success" });
      onOpenChange(false);
    } else if (job.status === "failed") {
      toast.push({
        title: "Ingestion failed",
        description: job.error ?? undefined,
        tone: "error",
      });
    }
  }, [job.status, job.error, jobId, toast, onOpenChange]);

  const onSubmit = async () => {
    if (!file) return;
    try {
      const result = await upload.mutateAsync({
        file,
        onProgress: (p) => setProgress(p),
      });
      if (result.job_id) {
        setJobId(result.job_id);
      } else {
        toast.push({ title: "Knowledge ingested", tone: "success" });
        onOpenChange(false);
      }
    } catch (e) {
      toast.push({
        title: "Upload failed",
        description: (e as Error).message,
        tone: "error",
      });
    }
  };

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <div className="p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Upload to general knowledge base</h2>
          <p className="text-xs text-muted-foreground mt-1">
            This document will be available to agents across <strong>all</strong> projects.
          </p>
        </div>
        <div
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
          }}
          onDragOver={(e) => e.preventDefault()}
          className="border-2 border-dashed border-border rounded-md p-8 text-center cursor-pointer hover:bg-muted/40"
          onClick={() => inputRef.current?.click()}
        >
          {file ? (
            <div className="space-y-1">
              <div className="font-medium text-sm">{file.name}</div>
              <div className="text-xs text-muted-foreground">{formatBytes(file.size)}</div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Drag and drop a PDF, DOCX, MD, TXT or click to select
            </p>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.md,.txt,.xlsx,.xlsm"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {(upload.isPending || progress > 0) && (
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Uploading: {progress}%</div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        {jobId && job.status && job.status !== "succeeded" && job.status !== "failed" && (
          <div className="text-xs text-muted-foreground">
            Ingesting on the server… (status: {job.status})
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onSubmit} disabled={!file || upload.isPending}>
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}
