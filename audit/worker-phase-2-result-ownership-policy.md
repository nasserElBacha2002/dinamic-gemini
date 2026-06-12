# Worker Phase 2 — Result Ownership and Retry Policy

**Status:** Updated after Part 3 — see implementation labels below.

Legend: **IMPLEMENTED** | **PARTIALLY_IMPLEMENTED** | **DEFERRED**

Evidence labels: `CONFIRMED_IN_MEMORY` | `CONFIRMED_IN_SQL_SERVER` | `PENDING_SQL_SERVER_VALIDATION`

---

## Rule 1 — Every processing attempt receives a new `job_id`

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | `RetryAisleJobUseCase` creates new UUID with `retry_of_job_id` lineage (P2-T003). |

---

## Rule 2 — Results attributable to creating `job_id`

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Rows scoped by `job_id`; transactional replace by scope (Part 2). Unique DB constraints **DEFERRED**. |

---

## Rule 3 — Only SUCCEEDED job becomes operational

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | `OperationalResultPromotionService` + CAS repository (Part 3, P2-P3-T001). |

---

## Rule 4 — FAILED/CANCELED rows not in operational UI

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Operational readers use `operational_job_id` via `ResultContextResolver`. `AUDIT_ALL` explicit only. |

---

## Rule 5 — Same `job_id` re-persist idempotent

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Transactional delete-and-replace UoW (Part 2). SQL: `PENDING_SQL_SERVER_VALIDATION`. |

---

## Rule 6 — Successful retry does not mix with failed attempt

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Per-job isolation + operational pointer on success job (P2-T003, Part 3 promotion). |

---

## Rule 7 — Historical results retained, non-operational

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Failed/non-operational rows retained; explicit `EXPLICIT_JOB` / `AUDIT_ALL` modes. |

---

## Rule 8 — Cleanup explicit, protects operational job

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | `CleanupJobResultsUseCase` rejects operational and active jobs (P2-P3-T008–T010). |

---

## Rule 9 — Read models resolve operational job consistently

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | List, export, aisle table use same resolver slice (P2-P3-T011). |

---

## Rule 10 — Aggregates must not combine attempts (operational views)

| Status | Notes |
| ------ | ----- |
| **IMPLEMENTED** | Operational views job-scoped; `AUDIT_ALL` explicit for admin aggregation. Persist rejects `"all"`. |

---

## Duplicate detection conventions (tests)

Unchanged — see `tests/support/worker_phase2/duplicate_detection.py`.

---

## Memory vs SQL

| Claim | Level |
| ----- | ----- |
| Idempotent same-job replace | `CONFIRMED_IN_MEMORY`; SQL `PENDING_SQL_SERVER_VALIDATION` |
| Operational promotion CAS | `CONFIRMED_IN_MEMORY`; SQL `PENDING_SQL_SERVER_VALIDATION` |
| Cleanup guards | `CONFIRMED_IN_MEMORY`; SQL `PENDING_SQL_SERVER_VALIDATION` |
