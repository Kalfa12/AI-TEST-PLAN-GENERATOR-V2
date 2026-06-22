# SF-EDGE Validation Strategy

Document ID: SF-EDGE-VAL-004  
Version: 1.2  
Date: 2026-05-02  
Owner: QA and Validation  
Project: Smart Factory Edge Gateway

## 1. Validation Objective

The objective of validation is to provide confidence that SF-EDGE can collect, buffer, forward, secure, and audit industrial telemetry under realistic operational conditions.

Validation shall focus on requirements that affect production continuity, traceability, configuration correctness, and cybersecurity.

## 2. Test Levels

### 2.1 Unit Tests

Unit tests cover:

- protocol configuration validators;
- telemetry normalization;
- retry delay calculation;
- event ID generation;
- redaction utilities;
- role permission checks.

### 2.2 Integration Tests

Integration tests cover:

- adapter to normalizer flow;
- normalizer to local buffer flow;
- local buffer to cloud forwarder flow;
- API to audit service flow;
- configuration versioning and rollback.

### 2.3 System Tests

System tests cover the gateway as a complete system using simulated devices and a simulated cloud endpoint.

### 2.4 Security Tests

Security tests cover authentication, authorization, TLS behavior, support grants, and diagnostic bundle redaction.

### 2.5 Long-Run Tests

Long-run tests cover continuous operation for at least 30 days under nominal load or a compressed endurance profile approved by QA.

## 3. Test Environment

The primary validation environment shall include:

- one reference gateway hardware unit;
- one simulated Modbus TCP device;
- one simulated OPC UA server;
- one MQTT broker;
- one HTTP sensor simulator;
- one cloud ingestion simulator;
- one NTP server or NTP simulator;
- log collection and metrics capture.

## 4. Core Validation Scenarios

### VAL-SCEN-001 Device Registration

Verify that a maintenance engineer can register a valid Modbus TCP device and that duplicate device IDs are rejected.

Requirements covered:

- REQ-FUNC-001;
- REQ-FUNC-002;
- SEC-REQ-010;
- SEC-REQ-031.

### VAL-SCEN-002 Telemetry Collection and Normalization

Verify that telemetry collected from Modbus TCP and OPC UA devices is normalized into the common schema.

Requirements covered:

- REQ-FUNC-003;
- REQ-NFR-005.

### VAL-SCEN-003 Cloud Outage and Local Buffering

Simulate a cloud outage lasting 2 hours while devices continue sending telemetry.

Expected result:

- telemetry collection continues;
- records are buffered locally;
- no records are lost;
- forwarding resumes when the cloud simulator becomes available.

Requirements covered:

- REQ-FUNC-004;
- REQ-FUNC-005;
- REQ-NFR-003.

### VAL-SCEN-004 Duplicate Prevention

Replay buffered records after a transient cloud failure and verify that duplicate telemetry records are not accepted by the cloud simulator.

Requirements covered:

- REQ-FUNC-005;
- REQ-NFR-005.

### VAL-SCEN-005 Device Health Degradation

Disconnect a registered device and verify that the health state becomes disconnected within 30 seconds after failure detection.

Requirements covered:

- REQ-FUNC-006;
- REQ-FUNC-007.

### VAL-SCEN-006 Configuration Versioning and Rollback

Apply a valid configuration update, then apply an invalid update, then roll back to the previous valid version.

Expected result:

- each update creates a configuration version;
- rollback restores the previous valid configuration;
- audit events remain immutable.

Requirements covered:

- REQ-FUNC-008;
- REQ-FUNC-009;
- SEC-REQ-031.

### VAL-SCEN-007 Diagnostic Redaction

Generate a diagnostic bundle containing known secret-like values.

Expected result:

- secrets are redacted;
- diagnostic file does not contain private keys, passwords, or API tokens;
- export operation is audited.

Requirements covered:

- REQ-FUNC-010;
- SEC-REQ-021;
- SEC-REQ-052.

### VAL-SCEN-008 Role-Based Access

Verify that:

- plant_operator cannot update device configuration;
- maintenance_engineer cannot manage users;
- site_admin can perform rollback;
- cloud_support_engineer cannot access diagnostics without a support grant.

Requirements covered:

- SEC-REQ-010;
- SEC-REQ-011.

### VAL-SCEN-009 Startup Readiness

Power-cycle the gateway and verify that telemetry collection starts within 90 seconds.

Requirements covered:

- REQ-NFR-001.

### VAL-SCEN-010 Buffer Capacity Alert

Fill the local buffer above 80 percent capacity and verify that a buffer capacity alert is generated.

Requirements covered:

- REQ-FUNC-004;
- REQ-FUNC-007.

## 5. Entry Criteria

Validation may start when:

- requirements are approved;
- API contracts are stable;
- simulated devices are available;
- test accounts are configured;
- logging and metrics capture are enabled.

## 6. Exit Criteria

Validation is complete when:

- all high-priority scenarios pass;
- no open critical or high defects remain;
- traceability matrix is updated;
- diagnostic bundle redaction evidence is archived;
- QA lead approves the validation report.

## 7. Defect Severity

Critical:

- telemetry loss;
- unauthorized administrative access;
- secrets exposed in diagnostics;
- gateway cannot start.

High:

- health state not updated;
- rollback failure;
- duplicate telemetry forwarding;
- audit event missing for privileged action.

Medium:

- incorrect alert message;
- delay above expected threshold but without data loss;
- non-critical UI inconsistency.

Low:

- cosmetic issue;
- spelling issue;
- non-blocking log formatting issue.

## 8. Traceability Expectation

Every validation scenario shall reference one or more requirements. Every high-priority requirement shall be covered by at least one validation scenario.

Coverage shall be reviewed before release.

