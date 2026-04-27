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

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!user) {
    if (!router.location.pathname.startsWith("/login")) {
      navigate({ to: "/login" });
    }
    return <Outlet />;
  }

  const onLogout = () => {
    clearTokens();
    window.location.assign("/login");
  };

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 border-r border-border bg-muted/30 flex flex-col">
        <div className="p-4 border-b border-border">
          <div className="font-semibold">Test Plan Generator</div>
          <div className="text-xs text-muted-foreground mt-1">{user.email}</div>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV.filter((n) => !n.adminOnly || user.is_admin).map((n) => {
            const active = router.location.pathname.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={cn(
                  "block rounded-md px-3 py-2 text-sm",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-foreground hover:bg-accent",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-2 border-t border-border">
          <Button variant="ghost" size="sm" className="w-full" onClick={onLogout}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
      <ToastViewport />
    </div>
  );
}
