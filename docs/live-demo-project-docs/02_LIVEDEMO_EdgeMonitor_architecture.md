# EdgeMonitor Gateway Architecture and API Notes

Document ID: LIVE-EDGE-ARCH-002  
Version: 1.0  
Date: 2026-06-22  
Project: EdgeMonitor Gateway Pilot  
Document type: Architecture and API specification  

## 1. Architecture Overview

EdgeMonitor Gateway is composed of local services running on one industrial gateway.

Main services:

- Device Manager;
- Protocol Adapter Runtime;
- Telemetry Normalizer;
- Local Buffer;
- Cloud Forwarder;
- Audit Service;
- Diagnostic Service.

The gateway shall continue collecting telemetry even when the cloud ingestion endpoint is unavailable.

## 2. Device Manager

The Device Manager stores registered devices and validates device configuration.

Device configuration fields:

- device_id;
- display_name;
- protocol;
- host;
- port;
- polling_interval_seconds;
- signal_map;
- enabled;
- configuration_version.

The Device Manager publishes a configuration change event after each successful update.

## 3. Protocol Adapter Runtime

The Protocol Adapter Runtime starts one adapter per enabled device.

Supported adapters for the pilot:

- ModbusTcpAdapter;
- MqttSubscriberAdapter;
- HttpJsonSensorAdapter.

If an adapter crashes three times within five minutes, the gateway shall mark the device as degraded and generate an operational alert.

## 4. Telemetry Normalizer

The Telemetry Normalizer receives raw protocol payloads and emits normalized telemetry records.

If a payload does not match the configured signal map, the record shall be rejected and a validation error shall be logged.

Rejected payloads shall not be forwarded to the cloud.

## 5. Local Buffer

The Local Buffer stores normalized telemetry before cloud forwarding.

Buffer behavior:

- records are ordered by original_timestamp then ingestion_timestamp;
- records are marked forwarded only after cloud acknowledgement;
- retry_count is tracked per record;
- records are not removed before successful forwarding unless retention limits are exceeded.

## 6. Cloud Forwarder

The Cloud Forwarder sends telemetry batches to the cloud ingestion endpoint.

Retry policy:

- initial retry delay: 1 second;
- multiplier: 2;
- maximum retry delay: 60 seconds;
- alert after 5 consecutive forwarding failures.

The forwarder shall use event_id as an idempotency key.

## 7. API Summary

### POST /api/v1/devices

Creates a device.

Required role:

- maintenance_engineer;
- site_admin.

Expected responses:

- 201 Created;
- 400 Invalid configuration;
- 401 Unauthenticated;
- 403 Forbidden;
- 409 Duplicate device ID.

### GET /api/v1/devices

Returns registered devices and health status.

Required role:

- plant_operator;
- maintenance_engineer;
- site_admin.

### PATCH /api/v1/devices/{device_id}

Updates device configuration and creates a new configuration version.

### POST /api/v1/configuration/rollback

Rolls back to the previous valid configuration version.

Required role:

- site_admin.

### POST /api/v1/diagnostics/export

Creates a diagnostic export.

Required role:

- site_admin.

Sensitive values shall be redacted before the file is written.

## 8. Observability

The gateway exposes:

- `/health/live`;
- `/health/ready`;
- adapter status;
- buffer capacity metric;
- forwarding retry metric;
- audit event stream.

## 9. Architecture Risks

Known risks:

- duplicate telemetry after partial cloud timeout;
- delayed device health transition for MQTT disconnects;
- accidental leakage of credentials in diagnostic logs;
- misconfigured polling intervals causing excessive load.

