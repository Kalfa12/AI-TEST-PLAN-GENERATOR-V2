# SF-EDGE Architecture and API Specification

Document ID: SF-EDGE-ARCH-002  
Version: 1.1  
Date: 2026-04-22  
Owner: Systems Architecture  
Project: Smart Factory Edge Gateway

## 1. System Overview

SF-EDGE is composed of local services running on the gateway hardware. Services communicate through an internal event bus and persist state in a local database.

The cloud platform is treated as an external dependency. Telemetry collection must continue even if cloud services are unreachable.

## 2. Logical Components

### 2.1 Device Manager

The Device Manager stores registered devices, validates protocol settings, and exposes device inventory APIs.

Responsibilities:

- create, update, and disable devices;
- validate signal maps;
- publish configuration change events;
- keep configuration version metadata.

### 2.2 Protocol Adapter Runtime

The Protocol Adapter Runtime starts one adapter instance per registered device.

Supported adapter types:

- ModbusTcpAdapter;
- OpcUaAdapter;
- MqttSubscriberAdapter;
- HttpSensorAdapter.

Each adapter publishes normalized telemetry events to the internal event bus.

### 2.3 Telemetry Normalizer

The Telemetry Normalizer converts raw protocol payloads into the common telemetry schema.

Required normalized fields:

- event_id;
- device_id;
- signal_id;
- original_timestamp;
- ingestion_timestamp;
- value;
- unit;
- quality;
- source_protocol.

### 2.4 Local Buffer

The Local Buffer persists telemetry records before cloud forwarding. The buffer must support chronological replay and duplicate prevention.

The reference implementation uses a local embedded database table named telemetry_buffer.

### 2.5 Cloud Forwarder

The Cloud Forwarder sends normalized telemetry to the cloud ingestion API.

It uses exponential backoff for transient failures:

- initial delay: 1 second;
- multiplier: 2;
- maximum delay: 60 seconds;
- maximum consecutive retries before alert: 5.

### 2.6 Audit Service

The Audit Service records security-relevant and configuration-relevant events.

Examples:

- user login;
- failed login;
- device registration;
- device update;
- configuration rollback;
- certificate update;
- diagnostic bundle export.

## 3. Event Flow

1. A protocol adapter reads or receives device data.
2. The adapter emits a RawTelemetryReceived event.
3. The Telemetry Normalizer validates and converts the payload.
4. The normalized record is written to the Local Buffer.
5. The Cloud Forwarder attempts delivery.
6. On success, the record is marked as forwarded.
7. On failure, the record remains buffered and retry metadata is updated.

## 4. Internal Event Types

### DeviceRegistered

Fields:

- event_id;
- device_id;
- actor_user_id;
- configuration_version;
- timestamp.

### TelemetryNormalized

Fields:

- event_id;
- device_id;
- signal_id;
- normalized_value;
- quality;
- timestamp.

### CloudForwardingFailed

Fields:

- event_id;
- failure_reason;
- retry_count;
- next_retry_at;
- affected_record_count.

### BufferCapacityWarning

Fields:

- event_id;
- used_percent;
- threshold_percent;
- timestamp.

## 5. API Endpoints

All API endpoints are served under `/api/v1`.

### POST /api/v1/devices

Creates a registered device.

Required role:

- maintenance_engineer;
- site_admin.

Request body:

```json
{
  "device_id": "mixer-01",
  "display_name": "Mixer Line 1",
  "protocol": "modbus_tcp",
  "host": "10.10.4.21",
  "port": 502,
  "polling_interval_seconds": 10,
  "signal_map": [
    {
      "signal_id": "temperature",
      "address": "40001",
      "unit": "C"
    }
  ]
}
```

Expected responses:

- 201 Created;
- 400 Invalid protocol configuration;
- 409 Duplicate device ID;
- 403 Insufficient permissions.

### GET /api/v1/devices

Returns all devices visible to the authenticated user.

### PATCH /api/v1/devices/{device_id}

Updates protocol configuration or signal map. Each successful update creates a new configuration version.

### POST /api/v1/configurations/{version}/rollback

Rolls back to a previous valid configuration version.

Required role:

- site_admin.

### GET /api/v1/health/devices

Returns device health statuses and last communication timestamps.

### POST /api/v1/diagnostics/bundle

Generates a diagnostic bundle.

Secrets must be redacted before the bundle is written to disk.

## 6. Data Model Summary

### devices

Primary key:

- device_id.

Important fields:

- protocol;
- host;
- port;
- polling_interval_seconds;
- enabled;
- current_configuration_version.

### telemetry_buffer

Primary key:

- event_id.

Important fields:

- device_id;
- signal_id;
- original_timestamp;
- ingestion_timestamp;
- payload_json;
- forwarded;
- retry_count.

### audit_events

Primary key:

- audit_event_id.

Important fields:

- actor_user_id;
- action;
- target_type;
- target_id;
- timestamp;
- metadata_json.

## 7. Security Architecture

The API uses bearer tokens issued by the local identity service.

Roles:

- plant_operator;
- maintenance_engineer;
- site_admin;
- cloud_support_engineer.

Administrative operations require site_admin. Diagnostic access by cloud support requires a temporary support grant.

## 8. Error Handling

Transient cloud errors shall not stop telemetry collection.

Permanent configuration errors shall mark the affected device as configuration_error.

If a protocol adapter crashes, the runtime shall restart it up to 3 times within 5 minutes. After the third crash, the device status is degraded and an alert is raised.

## 9. Observability

The system exposes:

- structured logs;
- service health endpoint;
- adapter status endpoint;
- buffer capacity metric;
- forwarding retry metric;
- audit event stream.

## 10. Architecture Notes

The gateway prioritizes local continuity over immediate cloud delivery. This means the Local Buffer is part of the critical path and must be covered by integration and stress tests.

