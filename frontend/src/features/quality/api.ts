import { http } from "@/lib/api/http";
import type {
  DefectCatalogResponse,
  DefectReport,
} from "@/lib/api/types";

export async function getPlanDefects(
  projectId: string,
  planId: string,
): Promise<DefectReport> {
  const res = await http.get<DefectReport>(
    `/projects/${projectId}/plans/${planId}/defects`,
  );
  return res.data;
}

export async function getJobDefects(jobId: string): Promise<DefectReport> {
  const res = await http.get<DefectReport>(`/jobs/${jobId}/defects`);
  return res.data;
}

export async function getDefectCatalog(): Promise<DefectCatalogResponse> {
  const res = await http.get<DefectCatalogResponse>(`/quality/catalog`);
  return res.data;
}
