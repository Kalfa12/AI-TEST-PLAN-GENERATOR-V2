# EdgeMonitor Gateway Requirements

Document ID: LIVE-EDGE-REQ-001  
Version: 1.0  
Date: 2026-06-22  
Project: EdgeMonitor Gateway Pilot  
Document type: Project requirements specification  

## 1. Product Context

EdgeMonitor Gateway is a pilot industrial IoT gateway used to collect telemetry from factory machines, buffer data locally during cloud outages, and forward validated records to a cloud analytics platform.

The gateway will be demonstrated on a simulated production line with three device types:

- temperature controller using Modbus TCP;
- vibration sensor using MQTT;
- energy meter using HTTP JSON API.

The project team needs a test plan that covers functional behavior, reliability during outages, security access control, and traceability from requirements to tests.

## 2. User Roles

### Plant Operator

The plant operator monitors machine status and acknowledges alerts. The operator shall not modify device configuration.

### Maintenance Engineer

The maintenance engineer registers devices, edits signal mappings, and validates telemetry collection.

### Site Administrator

The site administrator manages users, certificates, configuration rollback, and diagnostic exports.

## 3. Functional Requirements

### REQ-EM-001 Device Registration

The gateway shall allow a maintenance engineer to register a new device with a unique device ID, protocol type, host, port, polling interval, and signal map.

Acceptance notes:

- duplicate device IDs shall be rejected;
- unsupported protocol types shall be rejected;
- successful registration shall create an audit event.

### REQ-EM-002 Telemetry Normalization

The gateway shall normalize all telemetry records into a common schema containing:

- event_id;
- device_id;
- signal_id;
- original_timestamp;
- ingestion_timestamp;
- value;
- unit;
- quality;
- source_protocol.

### REQ-EM-003 Polling Interval Boundary

The gateway shall reject polling intervals below 1 second.

The default polling interval shall be 10 seconds when no polling interval is supplied.

### REQ-EM-004 Local Buffering

If the cloud ingestion endpoint is unavailable, the gateway shall buffer telemetry locally for at least 6 hours at a rate of 500 measurements per minute.

### REQ-EM-005 Chronological Replay

When cloud connectivity is restored, the gateway shall forward buffered telemetry in chronological order.

### REQ-EM-006 Duplicate Prevention

The gateway shall not forward duplicate telemetry records after a transient cloud timeout.

Each telemetry record shall use a stable event_id for idempotency.

### REQ-EM-007 Device Health State

The gateway shall update a device health state to disconnected within 30 seconds after communication failure is detected.

Allowed health states are:

- healthy;
- degraded;
- disconnected;
- configuration_error.

### REQ-EM-008 Buffer Capacity Alert

The gateway shall generate an alert when local buffer usage exceeds 80 percent for more than 60 seconds.

### REQ-EM-009 Configuration Versioning

Every device configuration update shall create an immutable configuration version.

### REQ-EM-010 Rollback

The site administrator shall be able to roll back to the previous valid configuration version.

Rollback shall not delete the failed configuration version from the audit history.

## 4. Security Requirements

### REQ-EM-011 Authenticated API Access

All API endpoints except `/health/live` shall require authentication.

Unauthenticated requests shall return HTTP 401.

### REQ-EM-012 Role-Based Authorization

The system shall enforce role-based authorization:

- plant_operator may read device status and acknowledge alerts;
- maintenance_engineer may register devices and edit signal maps;
- site_admin may manage users, rollback configuration, and export diagnostics.

### REQ-EM-013 Diagnostic Redaction

Diagnostic exports shall redact passwords, API tokens, private keys, bearer tokens, and cloud credentials.

### REQ-EM-014 TLS Validation

The cloud forwarder shall validate the cloud endpoint certificate chain before sending telemetry.

If TLS validation fails, telemetry shall remain buffered locally.

## 5. Non-Functional Requirements

### REQ-EM-015 Startup Readiness

After power-on, the gateway shall be ready to collect telemetry within 90 seconds.

### REQ-EM-016 Nominal Load

The gateway shall process at least 500 measurements per minute with CPU usage below 70 percent on the reference hardware.

### REQ-EM-017 Audit Retention

The system shall retain audit events for at least 180 days.

## 6. Out of Scope

The following items are out of scope for the pilot:

- machine learning inference at the edge;
- mobile application;
- multi-site orchestration;
- high-frequency vibration streaming above 1 kHz.

