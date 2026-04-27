import { http } from "@/lib/api/http";
import type { LineageResponse } from "@/lib/api/types";

export async function getLineage(
  artefactId: string,
  depth = 3,
): Promise<LineageResponse> {
  const res = await http.get<LineageResponse>(`/trace/${encodeURIComponent(artefactId)}`, {
    params: { depth },
  });
  return res.data;
}

export async function getProjectCoverage(
  projectId: string,
): Promise<Record<string, string[]>> {
  const res = await http.get<Record<string, string[]>>(
    `/projects/${projectId}/coverage`,
  );
  return res.data;
}

export interface ProjectGaps {
  project_id: string;
  uncovered_requirement_ids: string[];
}

export async function getProjectGaps(projectId: string): Promise<ProjectGaps> {
  const res = await http.get<ProjectGaps>(`/projects/${projectId}/gaps`);
  return res.data;
}
