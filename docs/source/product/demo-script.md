# Live Demo Script

This page gives a recommended live demo flow.

## Preparation

Before the demo:

1. start the backend and frontend;
2. verify that login works;
3. verify that the general knowledge base is populated;
4. prepare the live demo PDFs from `docs/live-demo-project-docs/pdf/`;
5. keep the seeded demo project as a fallback.

## Recommended Demo Project

Create a new project:

- Name: `EdgeMonitor Gateway Pilot`
- Description: `Industrial IoT gateway that collects factory telemetry, buffers data during cloud outages, and forwards validated records to a cloud analytics platform.`
- Industry: `Energy` or `Generic`

## Project Documents to Upload

Upload these documents into the project:

1. `01_LIVEDEMO_EdgeMonitor_requirements.pdf`
2. `02_LIVEDEMO_EdgeMonitor_architecture.pdf`
3. `03_LIVEDEMO_EdgeMonitor_incidents.pdf`

These documents are intentionally short enough for a live demo but realistic enough to produce useful requirements and test cases.

## Demo Flow

1. Show the login page and sign in.
2. Open the projects page.
3. Create the EdgeMonitor project.
4. Upload the three project PDFs.
5. Show the documents table and ingestion status.
6. Open the requirements view and show extracted requirements.
7. Ask the chatbot a project-context question.
8. Generate a test plan.
9. Show agent progress.
10. Open the generated plan.
11. Show test cases.
12. Show traceability and coverage.
13. Ask the chatbot about the latest generated plan.
14. Export the plan to PDF if time allows.

## Suggested Generation Goal

Use this goal during the demo:

```text
Generate a risk-based validation plan for the EdgeMonitor Gateway pilot, using the general knowledge base guidance for test plan structure, cybersecurity testing, industrial IoT testing patterns, and traceability. Prioritize local buffering, duplicate prevention, RBAC, diagnostic redaction, TLS validation, device health timing, and configuration rollback.
```

## Chat Questions Before Generation

Use one or two of these:

- `What project am I working on, and which documents are available in context?`
- `Which requirements are related to duplicate telemetry prevention?`
- `Which role is allowed to roll back configuration?`
- `Which incident is still open?`

## Chat Questions After Generation

Use one or two of these:

- `Summarize the latest generated test plan.`
- `Which requirements are covered by the latest plan?`
- `Which requirements look uncovered?`
- `Create one additional test idea for the open MQTT device health delay incident.`

## Fallback

If live generation is slow or the external LLM provider fails, use the seeded project:

`DEMO - SF-EDGE Industrial Gateway`

Explain that the seeded project exists only to make the demo robust. The real value is still the same workflow: document ingestion, AI generation, traceability, and contextual review.
