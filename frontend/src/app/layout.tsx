import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { useCurrentUser } from "@/features/auth/hooks";
import { clearTokens } from "@/lib/auth/storage";
import { ToastViewport } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { to: "/projects", label: "Projects" },
  { to: "/knowledge", label: "Knowledge base" },
  { to: "/traceability", label: "Traceability" },
  { to: "/admin", label: "Admin", adminOnly: true },
];

export function AppLayout() {
  const navigate = useNavigate();
  const { data: user, isLoading } = useCurrentUser();
  const router = useRouterState();
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  const initials = useMemo(() => {
    const source = user?.display_name?.trim() || user?.email?.trim() || "U";
    const parts = source.split(/\s+/).filter(Boolean);
    return (parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : source.slice(0, 2)).toUpperCase();
  }, [user?.display_name, user?.email]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (!profileMenuRef.current) return;
      if (!profileMenuRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (!isLoading && !user && !router.location.pathname.startsWith("/login")) {
      navigate({ to: "/login" });
    }
  }, [isLoading, navigate, router.location.pathname, user]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }

  if (!user) {
    return <Outlet />;
  }

  const onLogout = () => {
    clearTokens();
    window.location.assign("/");
  };

  return (
    <div className="flex min-h-screen flex-col bg-muted/20 lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-border bg-background lg:w-64 lg:border-b-0 lg:border-r">
        <div className="border-b border-border px-4 py-4">
          <div className="flex items-center gap-2">
            <img src="/sigmaxis-logo.png" alt="Sigmaxis" className="h-8 w-8 object-contain" />
            <div>
              <div className="text-sm font-semibold tracking-wide">Test Plan Generator</div>
              <div className="mt-0.5 text-xs text-muted-foreground">SIGMAXIS QA platform</div>
            </div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto p-2 lg:flex-1 lg:flex-col lg:space-y-1 lg:overflow-visible">
          {NAV.filter((n) => !n.adminOnly || user.is_admin).map((n) => {
            const active = router.location.pathname.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  "block whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-2">
          <div ref={profileMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setProfileMenuOpen((value) => !value)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md border border-border bg-background/80 px-3 py-2 text-left transition-colors hover:bg-accent",
                profileMenuOpen && "bg-accent",
              )}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{user.display_name}</div>
                <div className="truncate text-xs text-muted-foreground">{user.email}</div>
              </div>
              <span className="text-xs text-muted-foreground">v</span>
            </button>

            {profileMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-2 rounded-lg border border-border bg-background p-1 shadow-lg">
                <Link
                  to="/settings"
                  className="block rounded-md px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => setProfileMenuOpen(false)}
                >
                  Settings
                </Link>
                <button
                  type="button"
                  className="block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={onLogout}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <Outlet />
      </main>
      <ToastViewport />
    </div>
  );
}
