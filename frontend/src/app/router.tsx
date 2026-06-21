import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
} from "@tanstack/react-router";
import { AppLayout } from "./layout";
import { HomePage } from "@/features/home/home-page";
import { LoginForm } from "@/features/auth/login-form";
import { SignUpForm } from "@/features/auth/sign-up-form";
import { ProjectsPage } from "@/features/projects/projects-page";
import { ProjectDashboard } from "@/features/projects/project-dashboard";
import { PlanDetailPage } from "@/features/plans/plan-detail";
import { RunWorkspacePage } from "@/features/plans/run-workspace";
import { ChatPage } from "@/features/chat/chat-page";
import { TraceabilityGraphPage } from "@/features/traceability/graph-view";
import { AdminPage } from "@/features/admin/admin-page";
import { KnowledgePage } from "@/features/knowledge/knowledge-page";
import { SettingsPage } from "@/features/auth/api-keys-page";
import { readTokens } from "@/lib/auth/storage";

const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => (readTokens() ? <Navigate to="/projects" /> : <HomePage />),
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginForm,
});

const signUpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  component: SignUpForm,
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

const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings",
  component: SettingsPage,
});

const apiKeysRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/api-keys",
  component: () => <Navigate to="/settings" />,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  signUpRoute,
  appRoute.addChildren([
    projectsRoute,
    projectDetailRoute,
    planDetailRoute,
    runWorkspaceRoute,
    chatRoute,
    traceabilityRoute,
    knowledgeRoute,
    settingsRoute,
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
