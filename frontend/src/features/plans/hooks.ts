import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPlan,
  deletePlan,
  generateRequirementTestCase,
  getJobStatus,
  getPlan,
  getPlanCoverage,
  listPlans,
  schedulePlan,
  updateTestCaseStatus,
} from "./api";
import type { TestCaseStatus } from "@/lib/api/types";

export function usePlans(projectId: string | undefined) {
  return useQuery({
    queryKey: ["plans", projectId],
    queryFn: () => listPlans(projectId!),
    enabled: !!projectId,
    // Refresh every 4 s so a just-finished job shows up without manual reload.
    refetchInterval: 4_000,
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

export function useGenerateRequirementTestCase(projectId: string, planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requirementId: string) =>
      generateRequirementTestCase(projectId, planId, requirementId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plan", projectId, planId] });
      qc.invalidateQueries({ queryKey: ["plan-coverage", projectId, planId] });
      qc.invalidateQueries({ queryKey: ["plans", projectId] });
      qc.invalidateQueries({ queryKey: ["project-coverage", projectId] });
      qc.invalidateQueries({ queryKey: ["project-gaps", projectId] });
      qc.invalidateQueries({ queryKey: ["plan-defects", projectId, planId] });
    },
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

export function useDeletePlan(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => deletePlan(projectId, planId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans", projectId] }),
  });
}

export function useSchedulePlan(projectId: string, planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => schedulePlan(projectId, planId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plan", projectId, planId] });
      qc.invalidateQueries({ queryKey: ["plans", projectId] });
    },
  });
}

export function useUpdateTestCaseStatus(projectId: string, planId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      testCaseId: string;
      status: TestCaseStatus;
      status_note?: string | null;
    }) =>
      updateTestCaseStatus(projectId, planId, body.testCaseId, {
        status: body.status,
        status_note: body.status_note,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plan", projectId, planId] });
      qc.invalidateQueries({ queryKey: ["plans", projectId] });
    },
  });
}

/** Poll a background job until it reaches a terminal state. */
export function usePlanJobPolling(
  jobId: string | null,
  onDone: (planId: string | null) => void,
) {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const s = await getJobStatus(jobId);
          if (cancelled) return;
          setStatus(s.status);
          if (s.status === "succeeded") {
            const planId = (s.result?.plan_id as string) ?? null;
            onDone(planId);
            return;
          }
          if (s.status === "failed") {
            setError(s.error ?? "Job failed");
            onDone(null);
            return;
          }
        } catch (e) {
          if (!cancelled) setError((e as Error).message);
          return;
        }
        await new Promise((r) => setTimeout(r, 2_000));
      }
    };

    poll();
    return () => { cancelled = true; };
  }, [jobId, onDone]);

  return { status, error };
}
