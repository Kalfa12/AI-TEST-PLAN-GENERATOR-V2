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
