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
