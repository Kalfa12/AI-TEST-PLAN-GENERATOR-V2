const ACCESS_KEY = "atp.access";
const REFRESH_KEY = "atp.refresh";

export interface StoredTokens {
  access: string;
  refresh: string;
}

export function readTokens(): StoredTokens | null {
  const access = localStorage.getItem(ACCESS_KEY);
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!access || !refresh) return null;
  return { access, refresh };
}

export function writeTokens(tokens: StoredTokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  localStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
