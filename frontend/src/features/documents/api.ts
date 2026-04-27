import { http } from "@/lib/api/http";
import type {
  DocumentItem,
  DocumentListResponse,
  DocumentUploadAccepted,
  JobStatus,
} from "@/lib/api/types";

export interface UploadResult {
  // Synchronous (small file): document fields are populated.
  document?: DocumentItem;
  n_chunks?: number;
  n_requirements?: number;
  // Asynchronous (large file): job_id returned for polling.
  job_id?: string;
}

export async function listDocuments(projectId: string): Promise<DocumentItem[]> {
  const res = await http.get<DocumentListResponse>(
    `/projects/${projectId}/documents`,
  );
  return res.data.items;
}

export async function uploadDocument(
  projectId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await http.post<UploadResult | DocumentUploadAccepted>(
    `/projects/${projectId}/documents`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      },
    },
  );
  return res.data as UploadResult;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await http.get<JobStatus>(`/jobs/${jobId}`);
  return res.data;
}
