import { http } from "@/lib/api/http";
import type { Requirement, RequirementListResponse } from "@/lib/api/types";

export async function listRequirements(projectId: string): Promise<Requirement[]> {
  const res = await http.get<RequirementListResponse>(
    `/projects/${projectId}/requirements`,
  );
  return res.data.items;
}
