# SF-EDGE Incident and Change Log

Document ID: SF-EDGE-OPS-005  
Version: 0.9  
Date: 2026-05-09  
Owner: Operations Readiness  
Project: Smart Factory Edge Gateway

## 1. Purpose

This document records selected incidents, test findings, and change decisions observed during pre-release validation of SF-EDGE.

The objective is to provide operational context for future test planning and knowledge base queries.

## 2. Incident INC-2026-041: Duplicate Telemetry After Cloud Timeout

Date detected: 2026-04-29  
Severity: High  
Status: Fixed  
Related components:

- Local Buffer;
- Cloud Forwarder;
- cloud ingestion simulator.

### Description

During a simulated cloud timeout, the Cloud Forwarder retried a batch after the cloud simulator had already accepted part of the batch.

The simulator detected duplicate event IDs for 37 telemetry records.

### Root Cause

The forwarder marked the full batch as failed when the HTTP response timed out. It did not reconcile partial acceptance using event IDs.

### Fix

The forwarder now sends idempotency keys and reconciles accepted event IDs after timeout recovery.

### Regression Tests Required

- replay buffered telemetry after timeout;
- verify no duplicate records are accepted;
- verify retry_count is updated only for records still pending;
- verify audit log records the forwarding anomaly.

Related requirements:

- REQ-FUNC-005;
- REQ-NFR-005.

## 3. Incident INC-2026-047: Diagnostic Bundle Exposed Token-Like Value

Date detected: 2026-05-01  
Severity: Critical  
Status: Fixed  
Related components:

- Diagnostic Bundle;
- Redaction Utility;
- Audit Service.

### Description

A diagnostic bundle contained a token-like value in a nested JSON field named `cloud_debug_header`.

### Root Cause

The redaction utility scanned only known top-level keys. It did not recursively inspect nested JSON fields.

### Fix

Redaction now recursively scans strings and keys using secret pattern detection.

### Regression Tests Required

- nested JSON secret redaction;
- private key redaction;
- bearer token redaction;
- diagnostic export audit event;
- checksum recording for exported bundle.

Related requirements:

- REQ-FUNC-010;
- SEC-REQ-021;
- SEC-REQ-052.

## 4. Incident INC-2026-052: Device Health Update Delay

Date detected: 2026-05-04  
Severity: High  
Status: Open  
Related components:

- Protocol Adapter Runtime;
- Device Health Service.

### Description

During an OPC UA disconnect test, the device health status changed to disconnected after 47 seconds instead of the expected 30 seconds.

### Suspected Cause

The OPC UA adapter waits for two full session timeout cycles before reporting failure.

### Temporary Mitigation

The health service now displays degraded status after the first failed communication cycle.

### Tests Required

- OPC UA disconnect detection;
- Modbus disconnect detection;
- MQTT broker disconnect detection;
- HTTP sensor timeout detection.

Related requirements:

- REQ-FUNC-006;
- REQ-FUNC-007.

## 5. Change Decision CHG-2026-018: Buffer Retention

Date: 2026-05-05  
Decision owner: Product Engineering  
Status: Approved for version 1

### Decision

The version 1 buffer retention requirement remains 24 hours at 2,000 measurements per minute.

A 72-hour buffer target is deferred to a later release.

### Rationale

Reference hardware storage is limited to 64 GB. The 24-hour target is sufficient for the initial customer pilot.

Related requirement:

- REQ-FUNC-004.

## 6. Change Decision CHG-2026-019: Automatic Certificate Rotation

Date: 2026-05-06  
Decision owner: Cybersecurity Team  
Status: Deferred

### Decision

Automatic OPC UA certificate rotation is not included in version 1.

The gateway shall still alert administrators 14 days before certificate expiration.

Related requirement:

- SEC-REQ-022.

## 7. Operational Notes

Known high-value test areas:

- local buffering during cloud outage;
- duplicate prevention after transient failures;
- support grant expiration;
- diagnostic redaction;
- health state transition timing;
- audit completeness after configuration changes.

## 8. Useful Knowledge Base Questions

The following questions should return meaningful answers if the knowledge base is working correctly:

1. Which requirements are related to duplicate telemetry prevention?
2. What happened in incident INC-2026-047?
3. Which tests should be run for diagnostic bundle redaction?
4. Is 72-hour local buffering required in version 1?
5. Which roles can register a device?
6. What should happen if cloud TLS validation fails?
7. Which open issue affects device health timing?

