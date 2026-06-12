# Phase 2 Part 3 — Operational Promotion, Concurrency, and Failed-Result Policy

## 1. Executive Summary

| Field | Value |
| ----- | ----- |
| **Verdict** | `PART_3_COMPLETE_WITH_SQL_VALIDATION_PENDING` |
| **Promotion strategy** | `OperationalResultPromotionService` + compare-and-set repository |
| **Ordering rule** | `Job.created_at` (attempt creation order, not `finished_at`) |
| **Failed-result policy** | Retain non-operational history; operational reads exclude failed jobs |
| **Cleanup policy** | Explicit `CleanupJobResultsUseCase`; protects operational + active jobs |
| **Read-model alignment** | `ResultContextResolver` + `ResultReadMode`; export/list/aisle table agree |
| **Memory results** | P2-P3-T001–T013 pass (18 tests) |
| **SQL results** | P2-P3-T014, T016 implemented; skipped without isolated SQL |
| **Remaining gaps** | SQL concurrent promotion T015; artifact finalization (Phase 3) |

## 2. Promotion Policy

See `audit/worker-phase-2-operational-promotion-policy.md`.

## 3. Architecture

| Component | Role |
| --------- | ---- |
| `OperationalJobPromotionRepository` | Atomic CAS on `aisles.operational_job_id` |
| `MemoryOperationalJobPromotionRepository` | Thread-locked compare-and-set |
| `SqlOperationalJobPromotionRepository` | Conditional UPDATE vs current job `created_at` |
| `OperationalResultPromotionService` | Eligibility validation + delegation |
| `V3JobExecutionStateService.mark_success` | Promotes via service (production inventories) |
| `V3JobExecutionStateService.fail_job_and_aisle` | Suppresses stale aisle downgrade |
| `CleanupJobResultsUseCase` | Transactional job-scoped delete via UoW scope store |
| `ResultContextResolver` | `ResultReadMode` for operational vs audit |

## 4. Concurrency Matrix

| Race | Expected winner | Actual (memory) | Evidence |
| ---- | --------------- | --------------- | -------- |
| Older finishes after newer | Newer operational | REJECTED_STALE for older | P2-P3-T003 |
| Newer after older | Newer replaces | PROMOTED | P2-P3-T004 |
| Simultaneous promotion | Newer `created_at` | job-b wins | P2-P3-T005 |
| Late failure after newer success | Newer preserved | Aisle stays PROCESSED | P2-P3-T007 |
| Stale success | Job SUCCEEDED | Not downgraded | P2-P3-T006 |

## 5. Failed-Result Policy

| Class | Operational read | Cleanup |
| ----- | ---------------- | ------- |
| Incomplete (rollback) | N/A — no rows | N/A |
| FAILED complete | Excluded | Allowed if non-operational |
| SUCCEEDED non-operational | Excluded by default | Allowed |
| Operational | Included | **Rejected** |

## 6. Cleanup Matrix

| Job state | Operational? | Cleanup allowed? | Outcome |
| --------- | -------------: | ---------------: | ------- |
| SUCCEEDED | yes | no | REJECTED_OPERATIONAL_JOB |
| FAILED | no | yes | CLEANED |
| RUNNING/STARTING/CANCEL_REQUESTED | no | no | REJECTED_ACTIVE_JOB |

## 7. Read-Model Matrix

| Consumer | Mode | Resolved job | Consistent? |
| -------- | ---- | ------------ | ----------: |
| ListAislePositions | OPERATIONAL | `operational_job_id` | Yes — P2-P3-T011 |
| ExportInventoryCollector | OPERATIONAL | `operational_job_id` | Yes — P2-P3-T011 |
| ListAislesWithStatus | OPERATIONAL slice | same pointer | Yes — P2-P3-T011 |
| ResultContextResolver | AUDIT_ALL | `"all"` explicit | Yes — P2-P3-T012 |
| PersistAisleResult | exact job | rejects `"all"` | Yes — P2-P3-T013 |

## 8. SQL Evidence

| Item | Status |
| ---- | ------ |
| Compare-and-set (T014) | PENDING_SQL_SERVER_VALIDATION |
| Concurrent promotion (T015) | NOT_IMPLEMENTED (deferred) |
| Cleanup protection (T016) | PENDING_SQL_SERVER_VALIDATION |

## 9. Findings

### WKR-P2-P3-001

| Field | Value |
| ----- | ----- |
| Severity | Low |
| Status | Deferred |
| Evidence | T015 concurrent SQL promotion not implemented |
| Recommended | Add threaded SQL integration when DB available |

### WKR-P2-P3-002

| Field | Value |
| ----- | ----- |
| Severity | Low |
| Status | Documented |
| Evidence | Artifact upload failure after persist leaves domain rows |
| Recommended | Phase 3 artifact finalization |

## 10. Remaining Gaps

- SQL validation for T014–T016 on isolated database
- Artifact finalization / recovery (Phase 3)
- Unique constraints on business keys

## 11. Final Phase 2 Assessment

**PHASE_2_COMPLETE_WITH_SQL_VALIDATION_PENDING**

Part 3 functional block complete in memory. Part 2 SQL transactional tests and Part 3 SQL promotion tests remain pending isolated SQL Server before production approval.
