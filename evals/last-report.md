# Evaluation report

| Benchmark | Mode | Extract F1 | Defect recall | Time | Status |
|---|---|---|---|---|---|
| Synthetic aerospace SRS | static-only | — |  83.3% | 0.00s | ✓ |


## Synthetic aerospace SRS

_11 requirements spanning functional, safety, performance, interface, and regulatory kinds. Six requirements are deliberately defective (TBD, modality drift, universal qualifier, vague modifier, compound) to exercise the defect-detection path._

**Defect detection** — recall  83.3% (5 / 6)

_Missed defects:_
  - REQ-009 → `modality_drift`
