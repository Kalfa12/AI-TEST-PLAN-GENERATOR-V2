# SF-EDGE Product Requirements Document

Document ID: SF-EDGE-PRD-001  
Version: 1.3  
Date: 2026-04-18  
Owner: Product Engineering  
Project: Smart Factory Edge Gateway

## 1. Purpose

The Smart Factory Edge Gateway, named SF-EDGE, is an industrial gateway used to collect machine telemetry, normalize it, buffer it locally, and forward it to a cloud analytics platform.

The product is intended for small and medium manufacturing sites where machines use mixed protocols such as Modbus TCP, OPC UA, MQTT, and REST-based sensor adapters.

The gateway must continue operating during temporary network outages and must provide traceable logs for quality and maintenance teams.

## 2. Business Objectives

The product shall:

- reduce manual collection of machine production data;
- provide near real-time visibility into machine status;
- support predictive maintenance use cases;
- allow remote configuration by authorized users;
- preserve telemetry data during short connectivity outages;
- provide audit trails for configuration and operational events.

## 3. Users

### 3.1 Plant Operator

The plant operator monitors machine status and acknowledges operational alerts. This user does not modify protocol mappings or security settings.

### 3.2 Maintenance Engineer

The maintenance engineer configures device connections, validates signal mappings, and reviews device health.

### 3.3 Site Administrator

The site administrator manages users, roles, remote access, certificates, and site-level policies.

### 3.4 Cloud Support Engineer

The cloud support engineer can inspect diagnostic bundles only when the site administrator grants temporary access.

## 4. Functional Requirements

### REQ-FUNC-001 Device Registration

The gateway shall allow a maintenance engineer to register a new industrial device with a unique device ID, protocol type, IP address or hostname, polling interval, and signal map.

Acceptance criteria:

- a registered device appears in the device inventory within 5 seconds;
- duplicate device IDs are rejected;
- invalid IP addresses or hostnames are rejected;
- all registration events are stored in the audit log.

### REQ-FUNC-002 Supported Protocols

The gateway shall support the following protocols in version 1:

- Modbus TCP;
- OPC UA;
- MQTT subscriber mode;
- HTTP sensor adapter mode.

Protocol-specific settings shall be validated before the device is saved.

### REQ-FUNC-003 Telemetry Collection

The gateway shall collect telemetry according to each device polling interval.

The minimum polling interval is 1 second. The default polling interval is 10 seconds. Polling intervals below 1 second shall be rejected by the API.

### REQ-FUNC-004 Local Buffering

If the cloud connection is unavailable, the gateway shall buffer telemetry locally for at least 24 hours at a rate of 2,000 measurements per minute.

The buffer shall use a first-in-first-out eviction strategy when the storage limit is reached.

### REQ-FUNC-005 Forwarding to Cloud

When connectivity is restored, the gateway shall forward buffered telemetry in chronological order.

The gateway shall not forward duplicate telemetry records. Each telemetry record shall include a stable event ID.

### REQ-FUNC-006 Device Health

The gateway shall compute a health status for each registered device:

- healthy;
- degraded;
- disconnected;
- configuration_error.

Health status shall be updated within 30 seconds after a communication failure is detected.

### REQ-FUNC-007 Alerting

The gateway shall generate an alert when:

- a device is disconnected for more than 2 minutes;
- the local buffer exceeds 80 percent capacity;
- cloud forwarding fails for more than 5 consecutive retry attempts;
- certificate expiration is less than 14 days away.

### REQ-FUNC-008 Configuration Versioning

Every configuration update shall create a new immutable configuration version.

The user shall be able to compare the current configuration with the previous version.

### REQ-FUNC-009 Rollback

The gateway shall allow a site administrator to roll back to the previous valid configuration version.

Rollback shall not delete the failed configuration version from the audit history.

### REQ-FUNC-010 Diagnostic Bundle

The gateway shall generate a diagnostic bundle containing:

- system information;
- active configuration version;
- recent service logs;
- protocol adapter status;
- buffer statistics;
- last 100 audit events.

Sensitive secrets, passwords, private keys, and API tokens shall be redacted.

## 5. Non-Functional Requirements

### REQ-NFR-001 Startup Time

After power-on, the gateway shall be ready to collect telemetry within 90 seconds.

### REQ-NFR-002 Availability

The gateway software shall support continuous operation for at least 30 days without manual restart under nominal load.

### REQ-NFR-003 Performance

The gateway shall process at least 2,000 measurements per minute with CPU usage below 70 percent on the reference hardware.

### REQ-NFR-004 Time Synchronization

The gateway shall synchronize time using NTP. If NTP is unavailable, the gateway shall flag timestamps as unsynchronized.

### REQ-NFR-005 Data Integrity

Telemetry records shall preserve:

- original timestamp;
- ingestion timestamp;
- device ID;
- signal ID;
- value;
- quality flag;
- event ID.

### REQ-NFR-006 Security

All remote API access shall require authentication. Administrative actions shall require role-based authorization.

### REQ-NFR-007 Auditability

The system shall retain audit events for at least 180 days or until exported by the site administrator.

## 6. Constraints

The first production release targets an ARM-based industrial gateway with:

- 4 CPU cores;
- 8 GB RAM;
- 64 GB local storage;
- Linux-based operating system;
- dual Ethernet interfaces.

The system shall not depend on permanent internet connectivity for local telemetry collection.

## 7. Out of Scope for Version 1

The following items are out of scope:

- machine learning inference at the edge;
- direct PLC firmware updates;
- high-frequency vibration streaming above 10 kHz;
- multi-site orchestration;
- mobile application.

## 8. Open Questions

1. Should the buffer retention target increase from 24 hours to 72 hours for high-priority sites?
2. Should OPC UA certificate rotation be managed automatically?
3. Should alert acknowledgements be synchronized to the cloud when connectivity returns?

