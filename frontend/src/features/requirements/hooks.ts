import { useQuery } from "@tanstack/react-query";
import { listRequirements } from "./api";

export function useRequirements(projectId: string | undefined) {
  return useQuery({
    queryKey: ["requirements", projectId],
    queryFn: () => listRequirements(projectId!),
    enabled: !!projectId,
    staleTime: 60_000,
  });
}
