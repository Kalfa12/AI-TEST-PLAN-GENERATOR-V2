import { http } from "@/lib/api/http";
import type {
  DocumentItem,
  DocumentListResponse,
  DocumentUploadAccepted,
  JobStatus,
} from "@/lib/api/types";

export interface UploadResult {
  document?: DocumentItem;
  n_chunks?: number;
  n_requirements?: number;
  job_id?: string;
}

export async function listGeneralDocuments(): Promise<DocumentItem[]> {
  const res = await http.get<DocumentListResponse>("/general/documents");
  return res.data.items;
}

export async function uploadGeneralDocument(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await http.post<UploadResult | DocumentUploadAccepted>(
    `/general/documents`,
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

export async function deleteGeneralDocument(docId: string): Promise<void> {
  await http.delete(`/general/documents/${docId}`);
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await http.get<JobStatus>(`/jobs/${jobId}`);
  return res.data;
}
