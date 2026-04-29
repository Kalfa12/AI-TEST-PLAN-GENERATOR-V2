import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
} from "@tanstack/react-router";
import { AppLayout } from "./layout";
import { LoginForm } from "@/features/auth/login-form";
import { ProjectsPage } from "@/features/projects/projects-page";
import { ProjectDashboard } from "@/features/projects/project-dashboard";
import { PlanDetailPage } from "@/features/plans/plan-detail";
import { RunWorkspacePage } from "@/features/plans/run-workspace";
import { ChatPage } from "@/features/chat/chat-page";
import { TraceabilityGraphPage } from "@/features/traceability/graph-view";
import { AdminPage } from "@/features/admin/admin-page";
import { KnowledgePage } from "@/features/knowledge/knowledge-page";
import { ApiKeysPage } from "@/features/auth/api-keys-page";

const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => <Navigate to="/projects" />,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginForm,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  component: AppLayout,
});

const projectsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects",
  component: ProjectsPage,
});

const projectDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectId",
  component: ProjectDashboard,
});

const planDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectId/plans/$planId",
  component: PlanDetailPage,
});

const runWorkspaceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectId/runs/$jobId",
  component: RunWorkspacePage,
});

const chatRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/chat/$sessionId",
  component: ChatPage,
});

const traceabilityRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/traceability",
  component: TraceabilityGraphPage,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin",
  component: AdminPage,
});

const knowledgeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/knowledge",
  component: KnowledgePage,
});

const apiKeysRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/api-keys",
  component: ApiKeysPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  appRoute.addChildren([
    projectsRoute,
    projectDetailRoute,
    planDetailRoute,
    runWorkspaceRoute,
    chatRoute,
    traceabilityRoute,
    knowledgeRoute,
    apiKeysRoute,
    adminRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
