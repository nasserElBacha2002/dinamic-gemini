# Phase 2 Part 3 — Operational Promotion Policy

**Status:** IMPLEMENTED_IN_PART_3 (memory validated; SQL compare-and-set pending isolated DB)

Legend: **DESIRED_POLICY** | **CURRENT_BEHAVIOR** | **IMPLEMENTED_IN_PART_3** | **DEFERRED**

---

## Eligibility rules

| Rule | DESIRED_POLICY | IMPLEMENTED_IN_PART_3 |
| ---- | -------------- | --------------------- |
| Same aisle | Candidate `target_id` must equal aisle | Yes — `OperationalResultPromotionService` |
| `process_aisle` only | Other job types rejected | Yes |
| `SUCCEEDED` only | Active/failed/canceled rejected | Yes — P2-P3-T001 |
| Persistence complete | Required before promotion at `mark_success` | Yes — promotion after persist path |
| Ordering | Newer attempt wins, not finish time alone | Yes — `Job.created_at` ordering |
| Failed/canceled never operational | Non-success statuses rejected | Yes |
| Atomic promotion | Compare-and-set, no read-modify-write race | Yes — memory lock + SQL conditional UPDATE |
| No silent clear | Stale candidate cannot clear pointer | Yes — REJECTED_STALE |
| Manual promote | Same guards via `PromoteAisleOperationalJobUseCase` | Yes |

---

## Ordering rule (IMPLEMENTED_IN_PART_3)

**Key:** `inventory_jobs.created_at` (creation/attempt order).

A candidate may promote when:

1. `operational_job_id` is NULL, or
2. `operational_job_id == candidate_job_id` (idempotent), or
3. current operational job's `created_at` <= candidate's `created_at`.

A slower older job that finishes after a newer retry is **REJECTED_STALE** but remains **SUCCEEDED**.

---

## Stale success semantics (IMPLEMENTED_IN_PART_3)

| Event | Job status | Aisle `operational_job_id` |
| ----- | ---------- | -------------------------- |
| Newer job promotes | SUCCEEDED | newer job |
| Older job succeeds after | SUCCEEDED (unchanged) | stays newer |
| Older job fails late | FAILED | stays newer; aisle not downgraded |

---

## Failed-result retention (IMPLEMENTED_IN_PART_3)

| Class | Policy |
| ----- | ------ |
| Transactionally incomplete | Must not exist (Part 2 UoW rollback) |
| SUCCEEDED non-operational | Retained as history |
| FAILED complete snapshot | Retained; excluded from operational reads |
| Operational snapshot | `operational_job_id` slice only |

Cleanup: explicit `CleanupJobResultsUseCase`; rejects operational and active jobs.

---

## Read modes (IMPLEMENTED_IN_PART_3)

| Mode | Use |
| ---- | --- |
| `OPERATIONAL` | Default API reads via `operational_job_id` |
| `EXPLICIT_JOB` | Audit/history for one job |
| `AUDIT_ALL` | Explicit admin aggregation (`job_id_for_slice="all"`) |
| `LEGACY` | Null-job rows only |

Operational persistence rejects `job_id in {"all", "legacy_null"}`.

---

## DEFERRED

- Artifact publication failure retention policy (Phase 3)
- Long-term history retention TTL
- DB unique constraints on business keys
- Privileged admin override for promotion
