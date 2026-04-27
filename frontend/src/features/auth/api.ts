import { http } from "@/lib/api/http";
import type { TokenPair, User } from "@/lib/api/types";

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await http.post<TokenPair>("/auth/login", { email, password });
  return res.data;
}

export async function fetchMe(): Promise<User> {
  const res = await http.get<User>("/auth/me");
  return res.data;
}

export interface ApiKey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  key: string;
  created_at: string;
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await http.get<ApiKey[]>("/auth/api-keys");
  return res.data;
}

export async function createApiKey(name: string): Promise<ApiKeyCreated> {
  const res = await http.post<ApiKeyCreated>("/auth/api-keys", { name });
  return res.data;
}

export async function revokeApiKey(id: string): Promise<void> {
  await http.delete(`/auth/api-keys/${id}`);
}
