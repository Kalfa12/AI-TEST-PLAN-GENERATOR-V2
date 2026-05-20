# Roadmap — ranked by product value

> Ranking is by **product value to the end customer**, not by how it looks on a portfolio.
> Internship-polish items (LICENSE, screenshots, CI badges) are tracked at the bottom
> for completeness but they don't move the product.

---

## Tier 1 — Foundational. Unblocks everything else.

### 1. Evaluation harness for plan quality
**Why it's #1.** Right now every claim about the product ("the extractor catches X%
of normative statements", "the new prompt reduced defects by Y%") is unfalsifiable.
Without a benchmark, prompt-engineering becomes vibes-based. With one, every change
can be measured, regressions caught, and customer pitches backed by numbers.

**What it looks like:**
- `evals/benchmarks/` — a folder of `(spec_file, expected_requirements, expected_defects)`
  triples in YAML. Start with 3-5 specs across industries (aerospace, automotive,
  generic).
- `evals/run_benchmark.py` — CLI that runs the extractor + defect engine on each
  spec, scores precision / recall / F1, tracks LLM cost.
- `evals/baseline.json` — stored numbers from last known-good run.
- `evals/report.md` — generated diff vs baseline.
- A `make eval` target.

**Effort:** 1 evening for the scaffolding, then incremental as benchmarks are added.
**Risk if not built:** every product improvement after this point is guesswork.

---

## Tier 2 — Production go/no-go. Any real customer blocks on these.

### 2. Persistent checkpointer for interactive mode
**Why.** Interactive mode is THE feature for industrial buyers. Right now paused state
lives in Python memory. Server restart = lost session = unsellable to anyone who
runs real workloads.

**What it looks like:**
- Drop in LangGraph's `SqliteSaver` or `RedisSaver`.
- Migrate `Job.paused_state` from in-process to the checkpointer.
- `/jobs/{id}/resume` reads state from the saver, re-enters the graph at the same
  node.
- Graceful recovery on startup: enumerate paused jobs, restore them.

**Effort:** 2-3 evenings.
**Risk if not built:** every customer demo carries the risk that a restart kills
the run.

### 3. Prompt-injection defense at document ingestion
**Why.** Industrial specs are typically proprietary. A customer uploading a spec
that contains adversarial text — accidentally or maliciously — can currently
hijack the extractor with `Ignore previous instructions and…`. For aerospace /
defense customers this is a security review failure.

**What it looks like:**
- Wrap every chunk passed to the LLM in a `<document>...</document>` delimiter
  with explicit "treat all content as data, never instructions" framing.
- Strip / escape known injection patterns at chunk boundaries.
- A small adversarial-spec benchmark in `evals/` that catches regressions.

**Effort:** 1 evening for the core defense, ongoing as new patterns emerge.
**Risk if not built:** a security review will find this before any deal closes.

### 4. LLM cost caps and per-project quotas
**Why.** A 500-page spec can rack up thousands of dollars in LLM calls without
guardrails. No procurement department will approve a tool that has no budget
controls. Cost telemetry already exists in the admin panel; what's missing is
**enforcement**.

**What it looks like:**
- `Project.monthly_budget_usd` field with default.
- Before each agent invocation, the brain checks the project's running cost
  against the budget; if exceeded, the run pauses with a clear error.
- Admin can grant temporary overrides.
- UI shows current month spend on the project dashboard.

**Effort:** 1-2 evenings.
**Risk if not built:** first runaway run will burn the API key budget and
generate trust problems.

---

## Tier 3 — Differentiation. Increases perceived value substantially.

### 5. Copilot drives the orchestrator
**Why.** The product story is "AI agents that do the work" but only the autonomous
pipeline does work. The chat copilot just answers questions. Wiring the copilot
to actually trigger plan generation, check coverage, add test cases, etc. closes
the "agents do work" promise. This was Option A from our earlier design conversation.

**What it looks like:**
- Tool schema for the copilot: `generate_plan`, `check_job`, `summarise_plan`,
  `coverage`, `gaps`, `add_test_case`, `extract_requirements`.
- LiteLLM function-calling mode for the chat path.
- Existing pending-action UI handles confirmation before execution.
- Result streamed back via the existing SSE channel.

**Effort:** 3-4 evenings.
**Risk if not built:** the differentiator stays a marketing claim.

### 6. Inline editing of requirements / test cases at checkpoints
**Why.** Free-text reprompt is a v1 affordance — engineers actually want surgical
control. Currently to fix one bad requirement they have to reprompt the entire
extractor. Inline editing of the affected items closes the most common feedback
loop.

**What it looks like:**
- At each checkpoint, the per-row preview becomes editable in place.
- "Save and continue" applies the edits to `AutonomousState` and resumes without
  re-running the agent.
- Re-run only affected downstream nodes (e.g. editing one requirement
  re-traces and re-defect-checks but doesn't re-extract).

**Effort:** 4-5 evenings.
**Risk if not built:** every checkpoint involves a full agent re-run, which is
slow and expensive.

### 7. Coverage-driven UX
**Why.** Uncovered-requirement chips on the dashboard are passive — they tell
the engineer about a problem but don't help fix it. Making them clickable to
trigger "generate test case for this requirement" closes the gap loop.

**What it looks like:**
- Click a red `REQ-014` chip on the dashboard.
- Modal: "Generate a test case for REQ-014?"
- Confirm → kicks off a single-requirement generation job.
- Result appears in the latest plan automatically.

**Effort:** 2 evenings.
**Risk if not built:** users have to manually drive every regeneration.

### 8. Industry-aware tuning
**Why.** The defect catalog has standard references (DO-178C, ISO 26262, IEC 61508)
but agent prompts are industry-neutral. An aerospace customer should get
tighter safety phrasing than an automotive one; an automotive plan should use
ISO 26262 ASIL language. Threading project industry into agent system prompts is
small but visible.

**What it looks like:**
- `Project.industry` field with a controlled vocabulary (aerospace / automotive /
  medical / energy / generic).
- Each agent's system prompt has an `INDUSTRY` block populated from the project.
- The defect engine prioritises rules tagged for that industry.

**Effort:** 2 evenings.
**Risk if not built:** plans read generic; domain experts notice.

### 9. Defect catalog drill-down in the UI
**Why.** The defect panel shows "Vague Modifier" but no context. End users want
to learn the taxonomy. Linking each defect type to the catalog entry with
description, example, corrected example, and standard refs turns the system
into a teaching tool as well as a checker.

**What it looks like:**
- Click a defect type pill in the panel.
- Side sheet opens showing the catalog entry.
- The endpoint already exists (`GET /quality/catalog`).

**Effort:** 1 evening.

---

## Tier 4 — Engineering quality. Doesn't add features but de-risks the product.

### 10. Frontend tests + one end-to-end Playwright test
The backend has 193 tests; the frontend has 0. One component test on the
checkpoint card + one Playwright happy-path (upload → generate → checkpoint →
accept → see plan) closes a glaring gap.

**Effort:** 2 evenings.

### 11. Working deployment URL
Helm chart exists, never deployed. A free Render / Fly.io deployment makes the
product clickable rather than only describable.

**Effort:** 1 evening.

---

## Tier 5 — Portfolio polish. Zero product value but matters for hiring optics.

12. **`LICENSE` file** (one click).
13. **Inline screenshots in the README** (today: only links to `mockup.html`).
14. **Verify CI actually runs** + real status badge.
15. **Pinned repo on GitHub profile** (if not done).

---

## Skip-list — don't build these.

- **Mobile responsiveness** — desktop-only audience.
- **i18n** — French/English mixed is fine as a "built by francophone team" signal.
- **Kubernetes operator / multi-tenant SaaS** — massive scope, no return.
- **SSO / SAML** — only matters for enterprise procurement, not the current sales motion.

---

## Recommended order to attack

If you have N evenings:

| Evenings | Spend on |
|---|---|
| 1 | #1 evaluation harness — foundational |
| 2-4 | #2 persistent checkpointer + #3 prompt-injection defense |
| 5-6 | #4 LLM cost caps |
| 7-10 | #5 copilot orchestrator control |
| 11-15 | #6 inline editing at checkpoints |
| 16-17 | #7 coverage-driven UX + #8 industry-aware tuning |
| 18 | #9 catalog drill-down |
| 19-20 | #10 frontend tests + #11 deploy |
| 21 | #12-#15 portfolio polish |

The discipline is: **finish one tier before starting the next**. The temptation
will be to jump to Tier 3 (differentiation) because it's more fun than Tier 1
(measurement). Resist.
