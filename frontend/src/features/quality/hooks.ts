import { useQuery } from "@tanstack/react-query";
import { getDefectCatalog, getJobDefects, getPlanDefects } from "./api";

export function usePlanDefects(
  projectId: string | undefined,
  planId: string | undefined,
) {
  return useQuery({
    queryKey: ["plan-defects", projectId, planId],
    queryFn: () => getPlanDefects(projectId!, planId!),
    enabled: !!projectId && !!planId,
    staleTime: 5 * 60_000,
    // 404 means "no defect report yet" — that's normal for older plans.
    retry: false,
  });
}

export function useJobDefects(jobId: string | undefined) {
  return useQuery({
    queryKey: ["job-defects", jobId],
    queryFn: () => getJobDefects(jobId!),
    enabled: !!jobId,
    retry: false,
  });
}

export function useDefectCatalog() {
  return useQuery({
    queryKey: ["defect-catalog"],
    queryFn: getDefectCatalog,
    staleTime: 60 * 60_000,
  });
}
