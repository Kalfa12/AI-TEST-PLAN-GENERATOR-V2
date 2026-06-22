---
marp: true
theme: default
paginate: true
backgroundColor: #ffffff
style: |
  :root {
    --ink: #101828;
    --muted: #667085;
    --line: #d0d5dd;
    --soft: #f8fafc;
    --blue: #175cd3;
    --green: #067647;
    --amber: #b54708;
  }
  section {
    font-family: Inter, "Segoe UI", Arial, sans-serif;
    color: var(--ink);
    font-size: 1.02rem;
    line-height: 1.42;
    padding: 44px 58px;
  }
  h1 {
    color: var(--ink);
    font-size: 2.45rem;
    letter-spacing: 0;
    margin-bottom: 0.35em;
  }
  h2 {
    color: var(--ink);
    font-size: 1.75rem;
    margin-bottom: 0.55em;
  }
  h3 {
    color: var(--blue);
    font-size: 1.05rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.35em;
  }
  p, li { color: #344054; }
  strong { color: var(--ink); }
  code {
    background: #eef2f6;
    border: 1px solid #e4e7ec;
    border-radius: 4px;
    padding: 1px 5px;
    color: #344054;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    margin-top: 12px;
  }
  th {
    background: #111827;
    color: #ffffff;
    text-align: left;
    padding: 8px 10px;
    font-weight: 600;
  }
  td {
    border: 1px solid var(--line);
    padding: 7px 10px;
    vertical-align: top;
  }
  tr:nth-child(even) td { background: #f9fafb; }
  blockquote {
    border-left: 4px solid var(--blue);
    padding-left: 16px;
    color: var(--muted);
    margin-left: 0;
  }
  .lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .subtitle {
    color: var(--muted);
    font-size: 1.18rem;
    max-width: 780px;
  }
  .meta {
    color: var(--muted);
    font-size: 0.92rem;
    margin-top: 36px;
  }
  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 26px;
  }
  .grid3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }
  .card {
    border: 1px solid var(--line);
    background: var(--soft);
    border-radius: 8px;
    padding: 16px 18px;
  }
  .metric {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px 16px;
    background: #ffffff;
  }
  .metric .value {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--ink);
  }
  .metric .label {
    color: var(--muted);
    font-size: 0.86rem;
  }
  .tag {
    display: inline-block;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 4px 10px;
    margin: 3px 4px 3px 0;
    color: #344054;
    background: #ffffff;
    font-size: 0.82rem;
  }
  .blue { color: var(--blue); }
  .green { color: var(--green); }
  .amber { color: var(--amber); }
  .muted { color: var(--muted); }
---

<!-- _class: lead -->

# AI Test Plan Generator

<p class="subtitle">
A product-oriented AI platform that turns technical documents into requirements,
traceable test cases, and reviewable test plans.
</p>

<div class="meta">
Semester Project · `<course / school>` · `<team members>` · `<date>`
</div>

---

## 1. Product Vision

### From technical documents to engineering test plans

Most test plans start from long specifications, scattered requirements, and manual interpretation.

Our project explores how an AI system can support this workflow while keeping the important engineering constraints:

- **Grounding:** generated output should come from uploaded documents.
- **Traceability:** each test should link back to requirements and sources.
- **Control:** engineers should review and guide the pipeline.
- **Reuse:** project knowledge should remain available through the app.

> The goal is not to replace the test engineer.  
> The goal is to reduce repetitive drafting and make review easier.

---

## 2. The User Workflow

### What the demo shows

```mermaid
flowchart LR
    A["Create project"] --> B["Upload document"]
    B --> C["Extract requirements"]
    C --> D["Generate plan"]
    D --> E["Review test cases"]
    E --> F["Check coverage"]
    F --> G["Ask copilot"]
    G --> H["Export / improve"]
```

Each screen corresponds to a real backend artifact:

<span class="tag">Project</span>
<span class="tag">Document</span>
<span class="tag">Requirement</span>
<span class="tag">Test Plan</span>
<span class="tag">Test Case</span>
<span class="tag">Coverage Matrix</span>
<span class="tag">Chat Context</span>

---

## 3. Why This Is More Than A Chatbot

<div class="grid2">

<div class="card">

### Generic chatbot

- User pastes a prompt.
- Model generates text.
- No real project state.
- No stored artifacts.
- No reliable coverage.
- Hard to continue later.

</div>

<div class="card">

### Our platform

- Documents are uploaded and persisted.
- Requirements are extracted and stored.
- Test plans and test cases are reusable.
- Coverage is calculated.
- Chat retrieves project context.
- The workflow can continue over time.

</div>

</div>

---

## 4. System Architecture

### Full-stack application with an AI brain

```mermaid
flowchart LR
    UI["React + TypeScript\nProduct UI"]
    API["FastAPI\nREST + Events"]
    JOBS["Background Jobs\nLong AI tasks"]
    BRAIN["AI Brain\nMulti-agent pipeline"]
    MEMORY["Memory Layer\nDocuments, reqs, plans"]
    LLM["LLM Gateway\nDeepSeek / other providers"]
    DB["SQLite\nlocal MVP storage"]
    BLOBS["Blob Storage\nuploaded files"]

    UI --> API
    API --> JOBS
    JOBS --> BRAIN
    BRAIN <--> MEMORY
    BRAIN <--> LLM
    MEMORY <--> DB
    MEMORY <--> BLOBS
```

The app separates **product workflow**, **backend orchestration**, **AI reasoning**, and **persistence**.

---

## 5. The AI Brain

### Multi-agent pipeline

Instead of one large prompt, the system uses specialized agents:

| Agent | Product role |
|---|---|
| Document Analyst | Understand uploaded documents |
| Requirement Extractor | Extract structured requirements |
| Requirement Reviewer | Detect weak or vague requirements |
| Test Architect | Define plan strategy, scope, criteria, risks |
| Test Generator | Generate executable test cases |
| Traceability Agent | Build requirement-to-test coverage |
| Reviewer | Critique the generated plan |
| Planner | Use resources to schedule work |
| Copilot | Answer contextual project questions |

This makes the AI behavior easier to inspect, debug, and improve.

---

## 6. Generation Pipeline

### Behind the “Generate plan” button

```mermaid
flowchart TD
    A["Documents"] --> B["Chunking"]
    B --> C["Requirement extraction"]
    C --> D["Requirement review"]
    D --> E["Plan architecture"]
    E --> F["Test generation"]
    F --> G["Traceability"]
    G --> H["Quality review"]
    H --> I["Planning resources"]
    I --> J["Stored test plan"]
```

The optional **goal** is passed to the architect agent.

Useful goal:

> Validate authentication and authorization for the v2 API release.

Weak goal:

> Test plan.

If the user leaves it empty, the app uses a default complete-plan objective.

---

## 7. Traceability And Coverage

### The most important engineering feature

```mermaid
flowchart LR
    D["Source document"] --> C["Chunk"]
    C --> R["Requirement"]
    R --> T["Test case"]
    T --> P["Test plan"]
```

The platform stores links between:

- document chunks,
- extracted requirements,
- generated test cases,
- and the final test plan.

This enables:

- coverage percentage,
- uncovered requirements,
- source-aware review,
- and project-aware chat answers.

---

## 8. Project-Aware Copilot

### Chat with context, not just model memory

The copilot can use:

<div class="grid3">

<div class="metric">
  <div class="value">Docs</div>
  <div class="label">uploaded project documents</div>
</div>

<div class="metric">
  <div class="value">Reqs</div>
  <div class="label">stored requirements</div>
</div>

<div class="metric">
  <div class="value">Plan</div>
  <div class="label">latest generated test plan</div>
</div>

</div>

It also receives:

- project industry,
- retrieved document chunks,
- test cases,
- coverage matrix,
- recent chat history.

The UI shows a visible **chat context indicator** so the user knows what the chat is grounded on.

---

## 9. Product Screens To Demo

### Recommended live flow

1. **Login** and open the project dashboard.
2. Show **documents** and explain ingestion.
3. Show **requirements** and their role in generation.
4. Open **Generate plan** and explain goal + requirement basis.
5. Open an existing **test plan**.
6. Show **test cases** and detailed steps.
7. Show **coverage** and uncovered requirements.
8. Open **chat** and ask a project-specific question.
9. Mention **resources** for scheduling and follow-up.

Demo question:

> Based on the latest plan, which requirements are not covered and what tests should we add?

---

## 10. Product Features Implemented

| Area | Current capability |
|---|---|
| Project management | Projects, industry context, permanent delete |
| Document ingestion | Upload, chunk, store documents |
| Requirements | Extract, list, select for generation |
| Test plans | Generate, store, inspect, delete, export |
| Traceability | Requirement coverage and gaps |
| Chat | Project-aware copilot with context indicator |
| Planning | Resources and schedule assignments |
| Auth | Login, JWT, API keys, roles groundwork |
| Cost tracking | Token usage and local pricing table |

This gives us a working MVP-style product, not only an AI experiment.

---

## 11. Technical Highlights

<div class="grid2">

<div class="card">

### Backend

- FastAPI typed REST API.
- Background jobs for long AI tasks.
- SQLite persistence for local MVP.
- Artifact repositories for plans, requirements, documents.
- Budget and token tracking.

</div>

<div class="card">

### Frontend

- React + TypeScript.
- Project dashboard workflow.
- Query invalidation / auto-refresh for generated data.
- Interactive run workspace.
- Context-aware chat interface.

</div>

</div>

---

## 12. Current Limits

### Honest state of the project

The project is functional, but still a prototype/MVP.

Important limitations:

- SQLite is good for local demo, but not ideal for production multi-user usage.
- Long document ingestion can still create timeout-style UX issues.
- Backend chat history exists, but frontend chat session listing is still local-browser based.
- LLM pricing depends on maintaining provider/model price aliases.
- Generated plans still require human review before real engineering use.
- Some UX flows need more polish for a professional deployment.

These are clear next engineering priorities, not hidden assumptions.

---

## 13. What We Learned

### Main engineering lesson

Building an AI product is not just calling an LLM.

The hard parts are:

- getting the right context,
- storing intermediate artifacts,
- making generation auditable,
- showing progress and failures clearly,
- supporting user review,
- and keeping the UI aligned with backend reality.

The most important design choice was treating AI output as **managed project data**, not temporary chat text.

---

## 14. Conclusion

This project demonstrates a complete AI-assisted workflow for test plan generation:

- technical document ingestion,
- requirement extraction,
- multi-agent test plan generation,
- traceability and coverage,
- project-aware copilot,
- and a real product interface.

It is a strong foundation for a professional QA/V&V assistant.

**Next step:** improve robustness, polish the UX, and validate the generated plans with real engineering users.

