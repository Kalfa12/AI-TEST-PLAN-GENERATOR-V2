import { http } from "@/lib/api/http";
import type {
  ProviderKey,
  ProviderKeyCreated,
  ProviderName,
  TokenPair,
  User,
} from "@/lib/api/types";

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await http.post<TokenPair>("/auth/login", { email, password });
  return res.data;
}

export async function registerAccount(
  email: string,
  displayName: string,
  password: string,
): Promise<TokenPair> {
  const res = await http.post<TokenPair>("/auth/register", {
    email,
    display_name: displayName,
    password,
  });
  return res.data;
}

export async function fetchMe(): Promise<User> {
  const res = await http.get<User>("/auth/me");
  return res.data;
}

export async function updateMe(email: string, displayName: string): Promise<User> {
  const res = await http.patch<User>("/auth/me", {
    email,
    display_name: displayName,
  });
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

export async function listProviderKeys(): Promise<ProviderKey[]> {
  const res = await http.get<ProviderKey[]>("/auth/provider-keys");
  return res.data;
}

export async function createProviderKey(input: {
  provider: ProviderName;
  label: string;
  apiKey: string;
  isEnabled: boolean;
}): Promise<ProviderKeyCreated> {
  const res = await http.post<ProviderKeyCreated>("/auth/provider-keys", {
    provider: input.provider,
    label: input.label,
    api_key: input.apiKey,
    is_enabled: input.isEnabled,
  });
  return res.data;
}

export async function updateProviderKey(
  id: string,
  input: { label: string; isEnabled: boolean },
): Promise<ProviderKey> {
  const res = await http.patch<ProviderKey>(`/auth/provider-keys/${id}`, {
    label: input.label,
    is_enabled: input.isEnabled,
  });
  return res.data;
}

export async function revokeProviderKey(id: string): Promise<void> {
  await http.delete(`/auth/provider-keys/${id}`);
}
