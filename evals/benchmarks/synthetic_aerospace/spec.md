# Hydraulic Pump Controller — Software Requirements Specification (synthetic)

> Synthetic spec written for the evaluation harness. Deliberately mixes
> well-written requirements with common defects (TBD markers, vague modifiers,
> compound requirements, universal qualifiers, missing acceptance) so the
> harness can score both extraction recall and defect detection accuracy.

## 4.2 Functional requirements

### 4.2.1 Pressure regulation

REQ-001. The pump controller shall regulate the hydraulic line pressure within
±2 bar of the commanded setpoint during nominal operation.

REQ-002. The controller shall complete a pressure-loop cycle in less than 8 ms
under nominal CPU load.

REQ-003. The controller should report current pressure to the platform bus at a
rate of 50 Hz.

### 4.2.2 Safety and protection

REQ-004. The over-pressure protection circuit shall trip when measured line
pressure exceeds 285 bar for more than 100 ms.

REQ-005. The controller shall enter the SAFE state within 50 ms of detecting a
solenoid drive fault.

REQ-006. The controller shall log all DAL-B safety events to non-volatile memory.

### 4.2.3 Built-in test

REQ-007. The power-on built-in test (PBIT) shall complete in less than 3
seconds and report PASS/FAIL on the maintenance discrete output.

REQ-008. The controller shall always recover from a transient communication
loss within an appropriate time.

### 4.2.4 Interface (deliberately problematic)

REQ-009. The CAN-FD interface should be implemented and the message framing
shall conform to the platform ICD revision TBD.

REQ-010. The controller shall handle every fault condition.

## 5. Non-functional requirements

REQ-011. The software shall be developed under DO-178C objectives appropriate
for DAL-B.
