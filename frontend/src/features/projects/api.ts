import { http } from "@/lib/api/http";
import type { Project, ProjectListResponse } from "@/lib/api/types";

export async function listProjects(): Promise<Project[]> {
  const res = await http.get<ProjectListResponse>("/projects");
  return res.data.items;
}

export async function getProject(id: string): Promise<Project> {
  const res = await http.get<Project>(`/projects/${id}`);
  return res.data;
}

export async function createProject(body: {
  name: string;
  description?: string;
}): Promise<Project> {
  const res = await http.post<Project>("/projects", body);
  return res.data;
}

export async function updateProject(
  id: string,
  body: { name?: string; description?: string },
): Promise<Project> {
  const res = await http.patch<Project>(`/projects/${id}`, body);
  return res.data;
}

export async function archiveProject(id: string): Promise<void> {
  await http.delete(`/projects/${id}`);
}

export type ProjectRole = "owner" | "editor" | "reviewer" | "viewer";

export interface ProjectMember {
  project_id: string;
  user_id: string;
  role: ProjectRole;
  added_at: string;
}

export async function listMembers(projectId: string): Promise<ProjectMember[]> {
  const res = await http.get<ProjectMember[]>(`/projects/${projectId}/members`);
  return res.data;
}

export async function addMember(
  projectId: string,
  body: { user_id: string; role: ProjectRole },
): Promise<ProjectMember> {
  const res = await http.post<ProjectMember>(`/projects/${projectId}/members`, body);
  return res.data;
}

export async function removeMember(
  projectId: string,
  userId: string,
): Promise<void> {
  await http.delete(`/projects/${projectId}/members/${userId}`);
}
