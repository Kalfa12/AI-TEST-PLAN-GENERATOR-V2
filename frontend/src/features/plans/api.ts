import { http } from "@/lib/api/http";
import type {
  CoverageMatrixResponse,
  CreatePlanAccepted,
  JobStatus,
  PlanListItem,
  PlanListResponse,
  TestPlanSummary,
} from "@/lib/api/types";

export async function listPlans(projectId: string): Promise<PlanListItem[]> {
  const res = await http.get<PlanListResponse>(`/projects/${projectId}/plans`);
  return res.data.items;
}

export async function getPlan(
  projectId: string,
  planId: string,
  detail: "summary" | "full" = "full",
): Promise<TestPlanSummary> {
  const params = detail === "summary" ? { detail: "summary" } : undefined;
  const res = await http.get<TestPlanSummary>(
    `/projects/${projectId}/plans/${planId}`,
    { params },
  );
  return res.data;
}

export async function getPlanCoverage(
  projectId: string,
  planId: string,
): Promise<CoverageMatrixResponse> {
  const res = await http.get<CoverageMatrixResponse>(
    `/projects/${projectId}/plans/${planId}/coverage`,
  );
  return res.data;
}

export async function createPlan(
  projectId: string,
  body: { goal: string; detail_level: "summary" | "detailed" },
): Promise<CreatePlanAccepted> {
  const res = await http.post<CreatePlanAccepted>(
    `/projects/${projectId}/plans`,
    body,
  );
  return res.data;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await http.get<JobStatus>(`/jobs/${jobId}`);
  return res.data;
}

export async function deletePlan(projectId: string, planId: string): Promise<void> {
  await http.delete(`/projects/${projectId}/plans/${planId}`);
}

export async function exportPlanJson(
  projectId: string,
  planId: string,
): Promise<Blob> {
  const res = await http.get<Blob>(
    `/projects/${projectId}/plans/${planId}/export.json`,
    { responseType: "blob" },
  );
  return res.data;
}
