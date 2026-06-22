# Live Demo Project Documents

These files are project-specific inputs for a live demo of the AI Test Plan Generator.

Use them with the general knowledge base documents in `docs/general-knowledge-base/pdf/`.

## Recommended Project

Project name:

`EdgeMonitor Gateway Pilot`

Project description:

`Industrial IoT gateway that collects factory telemetry, buffers data during cloud outages, and forwards validated records to a cloud analytics platform.`

Industry:

`Energy` or `Generic`

## Upload Order

Upload these PDFs into the project, not into the general knowledge base:

1. `pdf/01_LIVEDEMO_EdgeMonitor_requirements.pdf`
2. `pdf/02_LIVEDEMO_EdgeMonitor_architecture.pdf`
3. `pdf/03_LIVEDEMO_EdgeMonitor_incidents.pdf`

The first file is enough for a short demo. Use all three when you want better traceability, richer risk analysis, and more relevant chatbot answers.

## Suggested Generation Goal

`Generate a risk-based validation plan for the EdgeMonitor Gateway pilot, using the general knowledge base guidance for test plan structure, cybersecurity testing, industrial IoT testing patterns, and traceability. Prioritize local buffering, duplicate prevention, RBAC, diagnostic redaction, TLS validation, device health timing, and configuration rollback.`

## Demo Chat Questions

Before generation:

- `What project am I working on, and which documents are available in context?`
- `Which requirements are related to duplicate telemetry prevention?`
- `Which role is allowed to roll back configuration?`
- `Which incident is still open?`

After generation:

- `Summarize the latest generated test plan.`
- `Which requirements are covered by tests and which look uncovered?`
- `Create one additional test idea for the open MQTT device health delay incident.`
- `Which tests should I show first in a stakeholder demo?`

## Demo Flow

1. Show that the general knowledge base is already populated.
2. Create the `EdgeMonitor Gateway Pilot` project.
3. Upload the three project PDFs.
4. Open the project documents or requirements view and show extracted content.
5. Ask one chatbot question before generation to prove project context retrieval.
6. Generate a plan with the suggested goal.
7. Show the generated plan, test cases, traceability, and coverage.
8. Ask one chatbot question after generation to prove it can see generated outputs.
9. Export the plan if there is time.

## Fallback

If the live AI generation is slow, switch to the seeded demo project:

`DEMO - SF-EDGE Industrial Gateway`

Use it as a backup only. For the strongest demonstration, the live flow should show upload, extraction, generation, traceability, and chatbot context.
