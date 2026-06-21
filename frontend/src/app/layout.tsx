import { useEffect } from "react";
import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { useCurrentUser } from "@/features/auth/hooks";
import { clearTokens } from "@/lib/auth/storage";
import { Button } from "@/components/ui/button";
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
  { to: "/api-keys", label: "API keys" },
  { to: "/admin", label: "Admin", adminOnly: true },
];

export function AppLayout() {
  const navigate = useNavigate();
  const { data: user, isLoading } = useCurrentUser();
  const router = useRouterState();

  useEffect(() => {
    if (!isLoading && !user && !router.location.pathname.startsWith("/login")) {
      navigate({ to: "/login" });
    }
  }, [isLoading, navigate, router.location.pathname, user]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Outlet />;
  }

  const onLogout = () => {
    clearTokens();
    window.location.assign("/login");
  };

  return (
    <div className="flex min-h-screen flex-col bg-muted/20 lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-border bg-background lg:w-64 lg:border-b-0 lg:border-r">
        <div className="border-b border-border px-4 py-4">
          <div className="text-sm font-semibold tracking-wide">SIGMAXIS QA</div>
          <div className="mt-1 text-xs text-muted-foreground">AI test planning platform</div>
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
        <div className="border-t border-border p-3 lg:block">
          <div className="mb-3 truncate text-xs text-muted-foreground">{user.email}</div>
          <Button variant="outline" size="sm" className="w-full" onClick={onLogout}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <Outlet />
      </main>
      <ToastViewport />
    </div>
  );
}
