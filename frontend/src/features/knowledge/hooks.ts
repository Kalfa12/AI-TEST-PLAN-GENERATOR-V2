import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteGeneralDocument,
  getJobStatus,
  listGeneralDocuments,
  uploadGeneralDocument,
  UploadResult,
} from "./api";

export function useGeneralDocuments() {
  return useQuery({
    queryKey: ["general-documents"],
    queryFn: listGeneralDocuments,
    refetchInterval: 4_000,
  });
}

export function useUploadGeneralDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { file: File; onProgress?: (pct: number) => void }) =>
      uploadGeneralDocument(params.file, params.onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["general-documents"] }),
  });
}

export function useDeleteGeneralDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) => deleteGeneralDocument(docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["general-documents"] }),
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
