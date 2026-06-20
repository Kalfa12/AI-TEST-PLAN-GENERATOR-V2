import { expect, test } from "@playwright/test";

const projectId = "proj-e2e";
const jobId = "job-e2e";
const sessionId = "sess-e2e";
const planId = "plan-e2e";

test("project upload to interactive checkpoint accept to plan detail", async ({ page }) => {
  const documents: unknown[] = [];
  let jobAccepted = false;

  await page.addInitScript(() => {
    window.localStorage.setItem("atp.access", "fake-access-token");
    window.localStorage.setItem("atp.refresh", "fake-refresh-token");
  });

  await page.route("http://localhost:8000/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (method === "GET" && path === "/auth/me") {
      return json({
        id: "usr-e2e",
        email: "demo@example.com",
        display_name: "Demo User",
        created_at: "2026-06-20T00:00:00Z",
        is_active: true,
        is_admin: true,
      });
    }

    if (method === "GET" && path === `/projects/${projectId}`) {
      return json({
        id: projectId,
        name: "E2E Demo Project",
        description: "Mocked demo path",
        industry: "aerospace",
        created_at: "2026-06-20T00:00:00Z",
        archived_at: null,
        owner_id: "usr-e2e",
        monthly_budget_usd: 100,
        budget_override_until: null,
        budget_override_usd: null,
        current_month_spend_usd: 0,
      });
    }

    if (method === "GET" && path === `/projects/${projectId}/documents`) {
      return json({ items: documents, total: documents.length, limit: 100, offset: 0 });
    }

    if (method === "POST" && path === `/projects/${projectId}/documents`) {
      const document = {
        id: "doc-e2e",
        title: "requirements.md",
        kind: "markdown",
        scope: "project",
        n_chunks: 2,
        ingested_at: "2026-06-20T00:00:00Z",
        source_uri: "requirements.md",
      };
      documents.splice(0, documents.length, document);
      return json({ document, n_chunks: 2, n_requirements: 1 });
    }

    if (method === "GET" && path === `/projects/${projectId}/plans`) {
      return json({
        items: jobAccepted
          ? [{ id: planId, title: "Aerospace Acceptance Plan", detail_level: "detailed", n_test_cases: 1 }]
          : [],
        total: jobAccepted ? 1 : 0,
      });
    }

    if (method === "POST" && path === `/projects/${projectId}/plans`) {
      return json({
        job_id: jobId,
        session_id: sessionId,
        message: "Interactive plan generation started.",
      });
    }

    if (method === "GET" && path === `/jobs/${jobId}`) {
      return json({
        id: jobId,
        kind: "run_autonomous_interactive",
        status: jobAccepted ? "succeeded" : "paused",
        session_id: sessionId,
        result: jobAccepted ? { plan_id: planId, n_test_cases: 1 } : null,
        error: null,
        created_at: "2026-06-20T00:00:00Z",
        updated_at: "2026-06-20T00:00:00Z",
        paused_at: jobAccepted ? null : "extractor",
      });
    }

    if (method === "GET" && path === `/jobs/${jobId}/checkpoint`) {
      return json({
        job_id: jobId,
        paused_at: "extractor",
        state: {
          requirements: [
            {
              id: "REQ-1",
              kind: "functional",
              priority: 3,
              title: "MFA requirement",
              statement: "The system shall require MFA for administrators.",
            },
          ],
        },
      });
    }

    if (method === "POST" && path === `/jobs/${jobId}/resume`) {
      jobAccepted = true;
      return json({
        id: jobId,
        kind: "run_autonomous_interactive",
        status: "succeeded",
        session_id: sessionId,
        result: { plan_id: planId, n_test_cases: 1 },
        error: null,
        created_at: "2026-06-20T00:00:00Z",
        updated_at: "2026-06-20T00:00:00Z",
        paused_at: null,
      });
    }

    if (method === "GET" && path === `/projects/${projectId}/plans/${planId}`) {
      return json({
        id: planId,
        project_id: projectId,
        title: "Aerospace Acceptance Plan",
        version: "v1",
        author: "AI Test Plan Generator",
        detail_level: "detailed",
        introduction: "Validate administrator authentication.",
        objectives: ["Verify MFA enforcement."],
        scope: "Authentication controls",
        out_of_scope: [],
        strategy: "Risk-based testing",
        entry_criteria: ["Specification approved"],
        exit_criteria: ["All critical tests pass"],
        risks: [],
        n_test_cases: 1,
        test_cases: [
          {
            id: "TC-1",
            title: "Administrator MFA challenge",
            objective: "Ensure administrators must complete MFA.",
            requirement_ids: ["REQ-1"],
            risk_level: 3,
            estimated_duration_minutes: 30,
            tags: [],
            status: "planned",
            source_evidence: [
              {
                relation: "verifies",
                document_id: "doc-e2e",
                chunk_id: "chunk-e2e",
                page_start: 1,
                page_end: 1,
                excerpt: "The system shall require MFA for administrators.",
              },
            ],
            steps: [
              {
                id: "step-1",
                index: 1,
                action: "Log in as an administrator.",
                expected_result: "MFA challenge is required.",
              },
            ],
            acceptance_criteria: [
              {
                id: "ac-1",
                statement: "MFA cannot be bypassed.",
                measurable: true,
              },
            ],
          },
        ],
        schedule: null,
      });
    }

    if (method === "GET" && path === `/projects/${projectId}/plans/${planId}/coverage`) {
      return json({ plan_id: planId, matrix: { "REQ-1": ["TC-1"] } });
    }

    if (method === "GET" && path === `/projects/${projectId}/plans/${planId}/defects`) {
      return json({ plan_id: planId, defects: [] });
    }

    if (method === "GET" && path === `/projects/${projectId}/coverage`) {
      return json({ "REQ-1": ["TC-1"] });
    }

    if (method === "GET" && path === `/projects/${projectId}/gaps`) {
      return json({ project_id: projectId, uncovered_requirement_ids: [] });
    }

    if (method === "GET" && path === `/projects/${projectId}/resources`) {
      return json({ items: [], total: 0 });
    }

    if (method === "GET" && path === `/projects/${projectId}/members`) {
      return json([]);
    }

    if (method === "GET" && path === `/sessions/${sessionId}/events`) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "\n",
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `No mock for ${method} ${path}` }),
    });
  });

  await page.goto(`/projects/${projectId}`);
  await expect(page.getByRole("heading", { name: "E2E Demo Project" })).toBeVisible();

  await page.getByRole("button", { name: "Upload" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "requirements.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Requirements\n\nThe system shall require MFA for administrators."),
  });
  await page.getByRole("button", { name: "Upload" }).last().click();
  await expect(page.getByText("requirements.md")).toBeVisible();

  await page.getByRole("button", { name: "Generate plan" }).click();
  await page.getByPlaceholder("e.g. Validate API authentication for v2 release").fill(
    "Validate administrator authentication",
  );
  await page.getByLabel("Interactive mode").check();
  await page.getByRole("button", { name: "Generate", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Plan generation workspace" })).toBeVisible();
  await expect(page.getByText("Checkpoint: Requirements extraction")).toBeVisible();
  await expect(page.getByText("MFA requirement")).toBeVisible();

  await page.getByRole("button", { name: "Accept and continue" }).click();
  await expect(page.getByText("Plan generation complete.")).toBeVisible();
  await page.getByRole("button", { name: "Open plan" }).click();

  await expect(page.getByRole("heading", { name: "Aerospace Acceptance Plan" })).toBeVisible();
  await page.getByText("Administrator MFA challenge").click();
  await expect(page.getByText("Source evidence")).toBeVisible();
  await expect(page.getByText("doc-e2e")).toBeVisible();
  await expect(page.getByText("The system shall require MFA for administrators.")).toBeVisible();
});
