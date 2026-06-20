import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addMember,
  archiveProject,
  createResource,
  createProject,
  deleteResource,
  getProject,
  listResources,
  listMembers,
  listProjects,
  removeMember,
  updateResource,
  updateProject,
  updateProjectBudget,
  type ProjectRole,
} from "./api";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: listProjects });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
    enabled: !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string }) =>
      updateProject(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", id] });
    },
  });
}

export function useUpdateProjectBudget(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      monthly_budget_usd: number;
      budget_override_usd?: number | null;
      budget_override_until?: string | null;
    }) => updateProjectBudget(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", id] });
    },
  });
}

export function useArchiveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: archiveProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useProjectMembers(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => listMembers(projectId!),
    enabled: !!projectId,
  });
}

export function useAddMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { user_id: string; role: ProjectRole }) =>
      addMember(projectId, body),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });
}

export function useRemoveMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeMember(projectId, userId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });
}

export function useResources(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project-resources", projectId],
    queryFn: () => listResources(projectId!),
    enabled: !!projectId,
  });
}

export function useCreateResource(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name: string;
      service: string;
      role?: string | null;
      availability_pct: number;
    }) => createResource(projectId, body),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["project-resources", projectId] }),
  });
}

export function useUpdateResource(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      id: string;
      name?: string;
      service?: string;
      role?: string | null;
      availability_pct?: number;
    }) => {
      const { id, ...payload } = body;
      return updateResource(projectId, id, payload);
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["project-resources", projectId] }),
  });
}

export function useDeleteResource(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (resourceId: string) => deleteResource(projectId, resourceId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["project-resources", projectId] }),
  });
}
