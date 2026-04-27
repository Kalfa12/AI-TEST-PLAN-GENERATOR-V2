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
