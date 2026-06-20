# Next Product Upgrades Roadmap

This roadmap is for coding agents taking over after the completed checkpoint
stack:

```text
main
 -> codex/phase-0-stabilization
 -> codex/phase-1-durable-artifacts
 -> codex/phase-2-ai-trust
 -> codex/phase-3-product-scope
 -> codex/phase-4-ingestion-security
```

The app is not complete yet. It is now an honest, safer prototype moving
toward an MVP. The next work should deepen the core product instead of adding
new decorative pages.

## Agent Rules

1. Create one branch per phase, stacked from the previous phase:
   `codex/phase-5-...`, `codex/phase-6-...`, etc.
2. Do not stage unrelated dirty files. Known unrelated files during this
   roadmap creation were:
   - `frontend/tsconfig.tsbuildinfo`
   - `src/ai_testplan_generator/quality/static_checks.py`
   - `PROJECT_AUDIT_REPORT_2026-06-18.md`
   - `output/`
3. Every phase must end with:
   - a commit,
   - backend tests,
   - frontend tests/build if frontend changed,
   - a short final summary with remaining dirty files.
4. Do not implement fake product flows. If a feature cannot truly mutate,
   persist, recover, audit, or enforce behavior, expose it as unsupported.
5. Prefer narrow, testable upgrades over broad rewrites.

## Current Product Boundary

Keep:
- Upload and ingest project/general documents.
- Extract requirements from uploaded source chunks.
- Generate test plans and test cases.
- Store generated artifacts durably enough to reload them.
- Show source evidence for generated tests.
- Run reviewer, defect, and traceability loops.
- Let the chatbot answer questions read-only with project context.

Treat as not yet complete:
- Restart-safe interactive checkpoints.
- Real chat-driven plan mutations.
- Real planning/resources/Gantt/follow-up.
- LLM spend enforcement.
- Production-grade security and deployment.
- Full end-to-end restart acceptance coverage.

## Phase 5 - Restart-Safe Interactive Checkpoints

### Objective

Make interactive plan generation survive process restarts. A paused checkpoint
must not live only in a Python `Job` object.

### Why This Is Next

Interactive checkpoints are central to the product promise. Today,
`src/ai_testplan_generator/pipelines/interactive_run.py` explicitly depends on
in-process `FakeJobQueue` state and `Job.paused_state`. That is acceptable for
tests, not for a customer demo or production-like deployment.

### Code Targets

- `src/ai_testplan_generator/api/jobs.py`
- `src/ai_testplan_generator/jobs/queue.py`
- `src/ai_testplan_generator/jobs/tasks/autonomous.py`
- `src/ai_testplan_generator/pipelines/interactive_run.py`
- `src/ai_testplan_generator/api/routers/plans.py`
- `src/ai_testplan_generator/domain/artifacts.py` or a new
  `src/ai_testplan_generator/domain/jobs.py`
- `tests/api/test_plans.py`
- `tests/api/test_jobs.py`

### Implementation Outline

1. Add durable job/checkpoint tables:
   - `jobs`: id, kind, status, session_id, project_id, result_json,
     error, created_at, updated_at, paused_at.
   - `job_checkpoints`: job_id, paused_at, state_json, directive_json,
     updated_at.
2. Persist `AutonomousState.model_dump(mode="json")` when pausing.
3. Make `/jobs/{job_id}/checkpoint` read the persisted checkpoint, not only
   `Job.paused_state`.
4. Make `/jobs/{job_id}/resume` store the directive durably and wake the
   in-process job when available.
5. On startup, expose paused jobs as paused even if no live task is currently
   waiting.
6. Decide and document the minimum restart behavior:
   - MVP option: paused job can be resumed only after worker recovery logic
     rehydrates it.
   - Better option: resume endpoint re-enters the interactive pipeline from
     the paused node.

### Acceptance Criteria

- A paused job remains visible after creating a new repository/app instance
  over the same SQLite DB.
- Checkpoint state returned after restart contains requirements/plan/test cases
  for the paused step.
- Resume of a non-paused job still returns a clear validation error.
- No API route relies on `app.state.jobs` as the only source of truth for
  paused checkpoint state.

### Tests

- Unit test for the job/checkpoint repository round trip.
- API test:
  1. create paused checkpoint,
  2. close/reopen repository,
  3. fetch `/jobs/{id}/checkpoint`,
  4. assert state is intact.
- Existing full backend suite.

### Do Not

- Do not claim Redis/ARQ support is restart-safe unless the resume path works
  outside `FakeJobQueue`.
- Do not store arbitrary Pydantic objects via pickle. Use JSON.

## Phase 6 - LLM Cost Caps And Project Quotas

### Objective

Prevent unbounded LLM spend per project.

### Why This Is Next

Cost telemetry exists in `src/ai_testplan_generator/telemetry/cost.py` and the
admin UI, but enforcement does not. A large uploaded spec can still trigger
many model calls with no budget guard.

### Code Targets

- `src/ai_testplan_generator/domain/projects.py`
- `src/ai_testplan_generator/config.py`
- `src/ai_testplan_generator/llm/litellm_gateway.py`
- `src/ai_testplan_generator/telemetry/cost.py`
- `src/ai_testplan_generator/agents/base.py`
- `src/ai_testplan_generator/api/routers/projects.py`
- `frontend/src/features/projects/project-dashboard.tsx`
- `frontend/src/features/admin/admin-page.tsx`
- `tests/telemetry/test_cost.py`
- `tests/api/test_projects.py`

### Implementation Outline

1. Add project fields:
   - `monthly_budget_usd`
   - `budget_override_until`
   - optional `budget_override_usd`
2. Add a cost lookup function for current-month project spend.
3. Add an enforcement hook before LLM calls or before agent invocation.
   Prefer checking in `BaseAgent.invoke` using `ctx.project_id`, then add a
   gateway-level fallback where project metadata is available.
4. Return a typed error when the budget is exceeded.
5. Surface budget/spend on the project dashboard.
6. Let admins set/override project budget.

### Acceptance Criteria

- Project with budget lower than current spend cannot start new LLM-backed
  generation.
- Error message is clear and includes project id and budget.
- Admin override allows generation until the override expires.
- Unknown/mock models do not create false positive spend in tests.

### Tests

- Cost summary current-month filter.
- Budget guard allows under-budget calls.
- Budget guard blocks over-budget calls.
- API test for project budget update.
- Frontend build.

### Do Not

- Do not merely display costs. This phase is enforcement.
- Do not hard-code budgets only in config; they must be project-specific.

## Phase 7 - End-To-End Acceptance And Restart Test

### Objective

Add a small real acceptance test proving the core product path works:
upload/ingest -> extract -> generate -> inspect plan -> trace source ->
restart/reload -> inspect again.

### Why This Is Next

Phases 1-4 improved pieces of the system. This phase proves they compose.

### Code Targets

- `tests/e2e/` or `tests/api/test_acceptance_flow.py`
- `tests/fixtures/`
- `src/ai_testplan_generator/domain/artifacts.py`
- `src/ai_testplan_generator/api/routers/documents.py`
- `src/ai_testplan_generator/api/routers/plans.py`
- `src/ai_testplan_generator/api/routers/traceability.py`

### Implementation Outline

1. Add a tiny Markdown or text specification fixture with 3-5 clear
   requirements and one adversarial line.
2. Use deterministic mock LLM behavior for extractor, architect, generator,
   reviewer, and traceability.
3. Run the flow through API or pipeline boundaries, not only direct model
   constructors.
4. Rebuild `Brain` and repositories against the same SQLite DB.
5. Assert the plan and source evidence still load after restart.

### Acceptance Criteria

- Generated plan has test cases.
- Each test case has source evidence.
- Traceability endpoint can find source lineage.
- After repository/brain reload, documents, requirements, plans, and test cases
  are still available.
- The adversarial line does not appear as an extracted requirement.

### Tests

- One focused E2E/acceptance test.
- Existing backend suite.

### Do Not

- Do not use live LLM calls.
- Do not test only internal memory objects; include API or repository reload.

## Phase 8 - Real Planning Or Remove Planning From MVP

### Objective

Choose one of two product directions:

- Build real planning/resources/follow-up.
- Or keep planning explicitly out of the MVP and remove misleading UI/API
  claims.

### Why This Is Next

The code has `Resource`, `TestSchedule`, and `PlannerAgent`, but Phase 3 made
the planner return an empty schedule when resources are absent. That was the
honest fix. The next step is either implement planning properly or stop showing
it as a product capability.

### Code Targets

- `src/ai_testplan_generator/models/planning.py`
- `src/ai_testplan_generator/agents/planner.py`
- `src/ai_testplan_generator/graphs/autonomous.py`
- `src/ai_testplan_generator/pipelines/interactive_run.py`
- `src/ai_testplan_generator/domain/artifacts.py`
- `frontend/src/features/plans/plan-detail.tsx`
- New frontend planning components if building the feature.

### Implementation Outline If Building

1. Add persisted resources:
   - name, role, service, availability, project_id.
2. Add resource CRUD API.
3. Pass project resources into `PlannerAgent`.
4. Persist `TestSchedule`.
5. Display schedule in plan detail.
6. Add status fields for test cases: not_started, planned, running, blocked,
   passed, failed.

### Acceptance Criteria If Building

- User can create resources for a project.
- Planner uses those resources and never invents unknown resource IDs.
- Schedule persists and reloads with the plan.
- Plan detail shows assignments and status.

### Tests If Building

- Planner rejects fabricated resource IDs.
- Resource CRUD API tests.
- Schedule persistence tests.
- Frontend build.

### Remove-From-MVP Alternative

- Keep `PlannerAgent` internal/disabled.
- Hide schedule UI if schedule is empty.
- Update docs to say planning is future scope.

### Do Not

- Do not reintroduce fabricated LLM schedules with empty resources.

## Phase 9 - Audited Chat Mutations

### Objective

Let the chatbot perform real, confirmed mutations against persisted plans.

### Why This Is Later

Phase 3 intentionally made chat read-only because fake confirmation was worse
than no mutation. Only implement this after persistence/checkpointing is solid.

### Code Targets

- `src/ai_testplan_generator/agents/copilot.py`
- `src/ai_testplan_generator/graphs/interactive.py`
- `src/ai_testplan_generator/pipelines/interactive.py`
- `src/ai_testplan_generator/api/routers/chat.py`
- `src/ai_testplan_generator/domain/artifacts.py`
- `src/ai_testplan_generator/api/middleware/audit.py`
- `frontend/src/features/chat/chat-page.tsx`

### Implementation Outline

1. Define explicit tool schemas:
   - `summarise_plan`
   - `check_coverage`
   - `add_test_case`
   - `revise_test_case`
   - `remove_test_case`
2. Store pending actions with session_id, user_id, project_id, payload,
   created_at, expires_at.
3. Confirmation endpoint must:
   - validate permissions,
   - apply mutation to persisted plan,
   - write audit event,
   - return changed artifact summary.
4. Update frontend pending-action banner to show a payload preview.

### Acceptance Criteria

- Chat can propose but not apply without confirmation.
- Confirmed mutation changes the persisted plan.
- Discarded mutation changes nothing.
- Every mutation has an audit event with before/after identifiers.
- Unauthorized user cannot confirm a mutation for another project.

### Tests

- Unit tests for tool payload validation.
- API tests for confirm/discard.
- RBAC tests.
- Artifact persistence reload after mutation.
- Frontend build.

### Do Not

- Do not let free-form LLM text directly mutate a plan.
- Do not store pending actions only in frontend localStorage.

## Phase 10 - Coverage-Driven Regeneration

### Objective

Make uncovered or weakly covered requirements actionable from the UI.

### Why

Traceability currently reports coverage, but the user must manually decide how
to repair gaps.

### Code Targets

- `src/ai_testplan_generator/agents/test_generator.py`
- `src/ai_testplan_generator/agents/traceability.py`
- `src/ai_testplan_generator/api/routers/plans.py`
- `src/ai_testplan_generator/domain/artifacts.py`
- `frontend/src/features/traceability/coverage-card.tsx`
- `frontend/src/features/plans/plan-detail.tsx`

### Implementation Outline

1. Add endpoint to generate a test case for one requirement against an
   existing plan.
2. Store the new test case durably and update coverage matrix.
3. Add UI action from uncovered requirement chip.
4. Re-run traceability/defect checks for affected plan only.

### Acceptance Criteria

- Clicking an uncovered requirement can generate a new test case.
- New test case appears in the plan without regenerating the whole plan.
- Source evidence is present.
- Coverage matrix updates.

### Tests

- API test for single-requirement generation.
- Persistence reload test.
- Frontend component or build test.

### Do Not

- Do not overwrite the whole plan when fixing one gap.

## Phase 11 - Industry-Aware Tuning

### Objective

Thread project industry through prompts and defect prioritization.

### Code Targets

- `src/ai_testplan_generator/domain/projects.py`
- `src/ai_testplan_generator/prompts/library.py`
- all agent prompt construction paths
- `src/ai_testplan_generator/models/defects.py`
- `frontend/src/features/projects/`

### Acceptance Criteria

- Project has controlled `industry`: generic, aerospace, automotive, medical,
  energy.
- Agent prompts include an industry block.
- Defect output can prioritize industry-relevant standards.
- UI allows setting industry on project create/edit.

### Tests

- Project schema/repository migration tests.
- Agent prompt tests for industry block.
- Frontend build.

## Phase 12 - Production Security Pass

### Objective

Close obvious production security gaps.

### Code Targets

- `src/ai_testplan_generator/config.py`
- `src/ai_testplan_generator/api/app.py`
- `src/ai_testplan_generator/api/security/`
- `src/ai_testplan_generator/api/routers/auth.py`
- `src/ai_testplan_generator/api/middleware/audit.py`
- `tests/api/test_auth.py`
- `tests/api/test_rbac.py`
- `tests/api/test_app.py`

### Implementation Outline

1. CORS:
   - In non-debug/prod mode, reject wildcard `API_CORS_ORIGINS=["*"]`.
2. Token revocation:
   - Add refresh/access token revocation table or Redis TTL store.
   - Make logout revoke refresh token.
3. Tenant isolation:
   - Audit every project/document/plan/trace/chat route for project membership.
4. Audit access:
   - Ensure sensitive read/write actions emit audit events with user/project id.
5. Secrets:
   - Add startup checks for insecure default JWT secret in production mode.

### Acceptance Criteria

- Production config cannot start with wildcard CORS and default JWT secret.
- Revoked token no longer works.
- Non-member cannot read project docs, plans, traceability, jobs, or chat.
- Audit table records sensitive writes.

### Tests

- Config/startup tests.
- Auth revocation tests.
- RBAC tests for each sensitive route.
- Full backend suite.

### Do Not

- Do not add enterprise SSO/SAML here.
- Do not start multi-tenant SaaS architecture beyond project isolation.

## Phase 13 - Frontend And E2E Confidence

### Objective

Give the UI enough tests to prevent accidental breakage in demos.

### Code Targets

- `frontend/src/features/plans/run-workspace.tsx`
- `frontend/src/features/plans/plan-detail.tsx`
- `frontend/src/features/chat/chat-page.tsx`
- `frontend/src/features/traceability/coverage-card.tsx`
- `frontend/src/test/`
- Playwright config if not already present.

### Acceptance Criteria

- Component test for checkpoint accept/reprompt/abort controls.
- Component test for source evidence rendering.
- Component test for unsupported chat action notice.
- One Playwright happy path with mocked backend:
  project -> upload -> generate -> checkpoint -> accept -> plan detail.

### Tests

- `npm test -- --run`
- `npm run build`
- Playwright test command added to package scripts.

## Phase 14 - Deployment Demo

### Objective

Make the app externally runnable for review/demo.

### Code Targets

- Dockerfiles and compose files if present.
- deployment docs.
- environment example files.
- health endpoints.

### Acceptance Criteria

- One documented deployment path works on Render, Fly.io, or a single VM.
- Health endpoint confirms API, DB, blob store, and optional Redis status.
- README has exact deployment steps and required env vars.

### Do Not

- Do not build a Kubernetes operator.
- Do not introduce complex multi-service production architecture unless needed
  for the chosen deployment target.

## Suggested Order

1. Phase 5 - restart-safe checkpoints.
2. Phase 6 - cost caps and project quotas.
3. Phase 7 - end-to-end acceptance/restart test.
4. Phase 8 - planning decision/build.
5. Phase 9 - audited chat mutations.
6. Phase 10 - coverage-driven regeneration.
7. Phase 11 - industry-aware tuning.
8. Phase 12 - production security pass.
9. Phase 13 - frontend/e2e confidence.
10. Phase 14 - deployment demo.

## MVP Definition

The app can be called MVP-complete when all of these are true:

- A user can upload documents, generate a plan, inspect test cases, and see
  source evidence.
- Generated artifacts persist across process restart.
- Interactive checkpoints survive restart or are explicitly disabled.
- The system fails loudly on empty extraction/generation.
- Prompt-injection boundaries exist for untrusted document text.
- Project access control protects documents, plans, jobs, chat, and traceability.
- LLM spend can be capped per project.
- At least one acceptance test proves the core flow end to end.

Anything beyond that is product expansion, not MVP completion.
