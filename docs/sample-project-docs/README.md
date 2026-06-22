# Sample Project Documents

These files provide a compact project corpus for testing the AI Test Plan Generator with realistic technical content.

Use them with the general knowledge base documents in `docs/general-knowledge-base/pdf/`.

## Sample Project

Project name:

`EdgeMonitor Gateway Pilot`

Project description:

`Industrial IoT gateway that collects factory telemetry, buffers data during cloud outages, and forwards validated records to a cloud analytics platform.`

Industry:

`Energy` or `Generic`

## Upload Order

Upload these PDFs into a project workspace, not into the general knowledge base:

1. `pdf/01_EdgeMonitor_requirements.pdf`
2. `pdf/02_EdgeMonitor_architecture.pdf`
3. `pdf/03_EdgeMonitor_incidents.pdf`

The first file is enough for a quick validation. Use all three when you want richer requirements, risk analysis, and chatbot answers.

## Suggested Generation Goal

```text
Generate a risk-based validation plan for the EdgeMonitor Gateway pilot, using the general knowledge base guidance for test plan structure, cybersecurity testing, industrial IoT testing patterns, and traceability. Prioritize local buffering, duplicate prevention, RBAC, diagnostic redaction, TLS validation, device health timing, and configuration rollback.
```

## Useful Chat Questions

Before generation:

- `What project am I working on, and which documents are available in context?`
- `Which requirements are related to duplicate telemetry prevention?`
- `Which role is allowed to roll back configuration?`
- `Which incident is still open?`

After generation:

- `Summarize the latest generated test plan.`
- `Which requirements are covered by tests and which look uncovered?`
- `Create one additional test idea for the open MQTT device health delay incident.`
