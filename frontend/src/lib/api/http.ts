import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { clearTokens, readTokens, writeTokens } from "@/lib/auth/storage";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const http: AxiosInstance = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const tokens = readTokens();
  if (tokens && !config.headers.has("Authorization")) {
    config.headers.set("Authorization", `Bearer ${tokens.access}`);
  }
  return config;
});

let refreshing: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const tokens = readTokens();
  if (!tokens) throw new Error("no refresh token");
  const res = await axios.post<{ access_token: string }>(
    `${baseURL}/auth/refresh`,
    { refresh_token: tokens.refresh },
  );
  writeTokens({ access: res.data.access_token, refresh: tokens.refresh });
  return res.data.access_token;
}

http.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      try {
        if (!refreshing) refreshing = refreshAccessToken();
        const newAccess = await refreshing;
        refreshing = null;
        original.headers.set("Authorization", `Bearer ${newAccess}`);
        return http.request(original);
      } catch (e) {
        refreshing = null;
        clearTokens();
        if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
          window.location.assign("/login");
        }
        throw e;
      }
    }
    return Promise.reject(error);
  },
);

export const wsBaseURL = import.meta.env.VITE_WS_BASE_URL ?? baseURL.replace(/^http/, "ws");
