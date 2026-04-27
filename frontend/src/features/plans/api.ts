import { http } from "@/lib/api/http";
import type {
  CoverageMatrixResponse,
  CreatePlanAccepted,
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
