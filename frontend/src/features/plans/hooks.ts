import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPlan,
  getPlan,
  getPlanCoverage,
  listPlans,
} from "./api";

export function usePlans(projectId: string | undefined) {
  return useQuery({
    queryKey: ["plans", projectId],
    queryFn: () => listPlans(projectId!),
    enabled: !!projectId,
  });
}

export function usePlan(
  projectId: string | undefined,
  planId: string | undefined,
  detail: "summary" | "full",
) {
  return useQuery({
    queryKey: ["plan", projectId, planId, detail],
    queryFn: () => getPlan(projectId!, planId!, detail),
    enabled: !!projectId && !!planId,
    staleTime: 5 * 60_000,
  });
}

export function usePlanCoverage(
  projectId: string | undefined,
  planId: string | undefined,
) {
  return useQuery({
    queryKey: ["plan-coverage", projectId, planId],
    queryFn: () => getPlanCoverage(projectId!, planId!),
    enabled: !!projectId && !!planId,
  });
}

export function useCreatePlan(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { goal: string; detail_level: "summary" | "detailed" }) =>
      createPlan(projectId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans", projectId] }),
  });
}
