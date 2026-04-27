import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJobStatus, listDocuments, uploadDocument, UploadResult } from "./api";
import { useEffect, useState } from "react";

export function useDocuments(projectId: string | undefined) {
  return useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => listDocuments(projectId!),
    enabled: !!projectId,
  });
}

export function useUploadDocument(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { file: File; onProgress?: (pct: number) => void }) =>
      uploadDocument(projectId, params.file, params.onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", projectId] }),
  });
}

export function useJobPolling(jobId: string | null) {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        try {
          const s = await getJobStatus(jobId);
          if (cancelled) return;
          setStatus(s.status);
          if (s.status === "succeeded" || s.status === "failed") {
            if (s.error) setError(s.error);
            return;
          }
        } catch (e) {
          if (!cancelled) setError((e as Error).message);
          return;
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [jobId]);
  return { status, error };
}

export type { UploadResult };
