import { http } from "@/lib/api/http";
import type {
  CheckpointResponse,
  CoverageMatrixResponse,
  CreatePlanAccepted,
  JobStatus,
  PlanListItem,
  PlanListResponse,
  TestCaseStatus,
  TestPlan,
  TestPlanSummary,
  TestSchedule,
} from "@/lib/api/types";

export async function listPlans(projectId: string): Promise<PlanListItem[]> {
  const res = await http.get<PlanListResponse>(`/projects/${projectId}/plans`);
  return res.data.items;
}

export async function getPlan(
  projectId: string,
  planId: string,
  detail: "summary",
): Promise<TestPlanSummary>;
export async function getPlan(
  projectId: string,
  planId: string,
  detail: "full",
): Promise<TestPlan>;
export async function getPlan(
  projectId: string,
  planId: string,
  detail: "summary" | "full",
): Promise<TestPlanSummary | TestPlan>;
export async function getPlan(
  projectId: string,
  planId: string,
  detail: "summary" | "full" = "full",
): Promise<TestPlanSummary | TestPlan> {
  const params = detail === "summary" ? { detail: "summary" } : undefined;
  const res = await http.get<TestPlanSummary | TestPlan>(
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
  body: {
    goal: string;
    detail_level: "summary" | "detailed";
    interactive?: boolean;
  },
): Promise<CreatePlanAccepted> {
  const res = await http.post<CreatePlanAccepted>(
    `/projects/${projectId}/plans`,
    body,
  );
  return res.data;
}

export async function getCheckpoint(jobId: string): Promise<CheckpointResponse> {
  const res = await http.get<CheckpointResponse>(`/jobs/${jobId}/checkpoint`);
  return res.data;
}

export async function resumeJob(
  jobId: string,
  body: { action: "accept" | "reprompt" | "abort"; feedback?: string },
): Promise<JobStatus> {
  const res = await http.post<JobStatus>(`/jobs/${jobId}/resume`, body);
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

export async function schedulePlan(
  projectId: string,
  planId: string,
): Promise<TestSchedule> {
  const res = await http.post<TestSchedule>(
    `/projects/${projectId}/plans/${planId}/schedule`,
  );
  return res.data;
}

export async function updateTestCaseStatus(
  projectId: string,
  planId: string,
  testCaseId: string,
  body: { status: TestCaseStatus; status_note?: string | null },
): Promise<void> {
  await http.patch(
    `/projects/${projectId}/plans/${planId}/test-cases/${testCaseId}/status`,
    body,
  );
}
