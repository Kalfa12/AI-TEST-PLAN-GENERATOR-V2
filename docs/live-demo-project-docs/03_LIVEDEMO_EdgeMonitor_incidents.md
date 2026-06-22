# EdgeMonitor Pilot Incident and Validation Notes

Document ID: LIVE-EDGE-OPS-003  
Version: 1.0  
Date: 2026-06-22  
Project: EdgeMonitor Gateway Pilot  
Document type: Incident and validation notes  

## 1. Purpose

This document records early validation findings from the EdgeMonitor pilot.

It should be used as project context when generating regression tests and risk-based test plans.

## 2. Incident INC-EM-001: Duplicate Telemetry After Cloud Timeout

Severity: High  
Status: Fixed  
Related requirements:

- REQ-EM-005;
- REQ-EM-006.

### Description

During a cloud timeout test, the cloud simulator accepted part of a telemetry batch, but the gateway retried the entire batch after the timeout.

The simulator detected duplicate event_id values for 12 telemetry records.

### Root Cause

The forwarder did not reconcile partial success after timeout recovery.

### Fix

The forwarder now uses event_id as an idempotency key and reconciles accepted records before retrying.

### Required Regression Tests

- replay buffered telemetry after partial timeout;
- verify duplicate records are not accepted;
- verify retry_count is updated only for pending records;
- verify forwarding anomaly appears in logs.

## 3. Incident INC-EM-002: Diagnostic Export Leaked Token-Like Header

Severity: Critical  
Status: Fixed  
Related requirements:

- REQ-EM-013;
- REQ-EM-017.

### Description

A diagnostic export contained a token-like value in a nested JSON field named `cloud_debug_header`.

### Root Cause

The redaction utility scanned known top-level keys but did not recursively inspect nested JSON fields.

### Fix

Redaction now recursively scans keys and values using secret pattern detection.

### Required Regression Tests

- nested JSON token redaction;
- bearer token redaction;
- private key redaction;
- export audit event;
- exported file checksum recording.

## 4. Incident INC-EM-003: MQTT Device Health Delay

Severity: Medium  
Status: Open  
Related requirements:

- REQ-EM-007.

### Description

During MQTT broker disconnect testing, device health changed to disconnected after 44 seconds instead of the required 30 seconds.

### Suspected Cause

The MQTT adapter waits for two missed heartbeat cycles before notifying the Device Health Service.

### Required Tests

- MQTT broker disconnect timing;
- Modbus TCP disconnect timing;
- HTTP sensor timeout timing;
- reconnect transition from disconnected to healthy.

## 5. Validation Priorities

The test plan should prioritize:

1. authentication and role-based access control;
2. local buffering during cloud outage;
3. duplicate telemetry prevention;
4. diagnostic redaction;
5. device health timing;
6. configuration versioning and rollback;
7. buffer capacity alerting.

## 6. Useful Demo Questions

The project chatbot should be able to answer:

- Which requirements are related to duplicate telemetry prevention?
- Which incident is still open?
- Which regression tests are required for diagnostic redaction?
- What should happen if TLS validation fails?
- Which role can roll back configuration?
- What are the highest-priority test areas?

