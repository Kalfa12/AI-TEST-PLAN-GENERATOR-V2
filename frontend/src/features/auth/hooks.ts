import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "./api";
import { readTokens } from "@/lib/auth/storage";
import type { User } from "@/lib/api/types";

export function useCurrentUser() {
  return useQuery<User | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      if (!readTokens()) return null;
      return fetchMe();
    },
    staleTime: 60_000,
  });
}
