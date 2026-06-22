import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useJobPolling, useUploadDocument } from "./hooks";
import { formatBytes } from "@/lib/utils";

export function UploadDrawer({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const upload = useUploadDocument(projectId);
  const toast = useToast();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJobPolling(jobId);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset state on open/close.
  useEffect(() => {
    if (!open) {
      setFile(null);
      setProgress(0);
      setJobId(null);
    }
  }, [open]);

  // Notify on async-job completion.
  useEffect(() => {
    if (!jobId) return;
    if (job.status === "succeeded") {
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
      queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-coverage", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-gaps", projectId] });
      queryClient.invalidateQueries({ queryKey: ["chat-context", projectId] });
      toast.push({ title: "Ingestion complete", tone: "success" });
      onOpenChange(false);
    } else if (job.status === "failed") {
      toast.push({
        title: "Ingestion failed",
        description: job.error ?? undefined,
        tone: "error",
      });
    }
  }, [job.status, job.error, jobId, projectId, queryClient, toast, onOpenChange]);

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
        toast.push({ title: "Document ingested", tone: "success" });
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

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
  };

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <div className="p-6 space-y-4">
        <h2 className="text-lg font-semibold">Upload document</h2>
        <div
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
          className="border-2 border-dashed border-border rounded-md p-8 text-center cursor-pointer hover:bg-muted/40"
          onClick={() => inputRef.current?.click()}
        >
          {file ? (
            <div className="space-y-1">
              <div className="font-medium text-sm">{file.name}</div>
              <div className="text-xs text-muted-foreground">
                {formatBytes(file.size)}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Drag and drop a PDF or click to select
            </p>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.md,.txt"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {(upload.isPending || progress > 0) && (
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">
              Uploading: {progress}%
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {jobId && job.status && job.status !== "succeeded" && job.status !== "failed" && (
          <div className="text-xs text-muted-foreground">
            Ingesting on the server… (status: {job.status})
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={!file || upload.isPending}>
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}
