import { http } from "@/lib/api/http";
import type { CostSummaryRow, DeadLetterListResponse } from "@/lib/api/types";

export async function listDeadLetter(): Promise<DeadLetterListResponse> {
  const res = await http.get<DeadLetterListResponse>("/admin/jobs/deadletter");
  return res.data;
}

export async function requeueDeadLetter(jobId: string): Promise<{ job_id: string }> {
  const res = await http.post<{ job_id: string }>(
    `/admin/jobs/deadletter/${encodeURIComponent(jobId)}/requeue`,
  );
  return res.data;
}

export async function getCosts(params: {
  from: string;
  to: string;
  group_by: "project" | "user" | "model";
}): Promise<CostSummaryRow[]> {
  const res = await http.get<CostSummaryRow[]>("/admin/costs", { params });
  return res.data;
}
