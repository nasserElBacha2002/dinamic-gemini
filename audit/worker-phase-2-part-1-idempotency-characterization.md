# Worker Phase 2 Part 1 — Idempotency Characterization Report

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Verdict** | `PART_1_COMPLETE_WITH_SQL_GAPS` |
| **Tests** | 5 component + 1 optional SQL (positions-only) |
| **Memory/component** | 5/5 PASS |
| **SQL Server** | P2-T001-SQL-POSITIONS **SKIPPED** (`PENDING_SQL_VERIFICATION`) |
| **Same-job idempotency** | **NON_IDEMPOTENT** (append + semantic SKU repetition) |
| **Changed-report behavior** | **APPEND_ONLY** positions/products/evidence/raw; **PARTIAL_REPLACEMENT** normalized/final |
| **Retry isolation** | **ISOLATED_BY_JOB_ID** via real executor failure + `RetryAisleJobUseCase` |
| **Read-model leakage** | Operational readers **ISOLATED**; `job_scope="all"` **LEAKS** (exact counts proven) |
| **Recommended Part 2** | Delete-and-replace by `job_id` inside transactional UnitOfWork |

**Production files modified:** 0

---

## 2. Test Inventory

| Test ID | Test | Type | Result | Evidence level |
|---------|------|------|--------|----------------|
| P2-T001 | `test_p2_t001_same_job_identical_persist_is_non_idempotent` | DIRECT_PERSIST | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T002 | `test_p2_t002_same_job_changed_report_appends_stale_and_new_rows` | DIRECT_PERSIST | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T003 | `test_p2_t003_real_failed_job_retry_isolates_all_layers` | EXECUTOR+RETRY | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T003-ALL-SCOPE | `test_p2_t003_all_scope_recompute_mixes_failed_and_success_raw_labels` | RECOMPUTE | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T001-SQL-POSITIONS | `test_p2_t001_sql_positions_same_job_identical_persist_duplicates_rows` | SQL | SKIP | `PENDING_SQL_VERIFICATION` |

Phase 1 regression: 18 passed, 2 skipped (unchanged).

---

## 3. Same-Job Idempotency Matrix (P2-T001)

| Layer | Run 1 | Run 2 | Structural dup | Semantic repetition | Classification |
|-------|------:|------:|----------------|---------------------|----------------|
| Positions | 2 | 4 | `entity_uid` ×2 | — | **NON_IDEMPOTENT** |
| Products | 2 | 4 | none (new `position_id`) | SKU ×2 | **NON_IDEMPOTENT** |
| Evidence | 2 | 4 | none | path ×2 | **NON_IDEMPOTENT** |
| Raw labels | 2 | 4 | none | `source_reference` ×2 | **APPEND_ONLY** |
| Normalized | 2 | 4 | none | SKU ×2 | **PARTIAL_REPLACEMENT** |
| Final counts | 2 | 4 | none | SKU ×2 | **PARTIAL_REPLACEMENT** |

---

## 4. Changed-Report Behavior (P2-T002)

| Layer | Updated in-place | Duplicated | Stale retained | Classification | Evidence |
|-------|-----------------|-------------|----------------|----------------|----------|
| Positions | No | A ×2 | B (qty 4) | APPEND_ONLY | `CONFIRMED_IN_COMPONENT_TEST` |
| Products | No | A on 2 positions | B product qty 4 | APPEND_ONLY | `CONFIRMED_IN_COMPONENT_TEST` |
| Evidence | No | A paths on 2 positions | B `crop_b.jpg` | APPEND_ONLY | `CONFIRMED_IN_COMPONENT_TEST` |
| Raw labels | No | e1 ×2 | e2 ×1 | APPEND_ONLY | `CONFIRMED_IN_COMPONENT_TEST` |
| Normalized | Rebuilt | SKU-A ×2 | SKU-B ×1, SKU-C ×1 | PARTIAL_REPLACEMENT | `CONFIRMED_IN_COMPONENT_TEST` |
| Final counts | Rebuilt | SKU-A ×2 (qty 1 each) | SKU-B, SKU-C qty 1 | PARTIAL_REPLACEMENT | `CONFIRMED_IN_COMPONENT_TEST` |

**Note:** `final_count.quantity` reflects label-merge count (1 per normalized label), not `product.detected_quantity`. Product rows carry detected quantities 2/99 for A.

---

## 5. Retry Isolation Matrix (P2-T003)

First attempt: `V3JobExecutor` + `FailingRecomputeUseCase` → `FAILED` with positions/products/evidence/raw persisted.  
Retry: `RetryAisleJobUseCase` → new job → executor success → `operational_job_id` set.

| Layer | Failed job | Success job | Mixed operationally? | Cleanup |
|-------|----------:|------------:|---------------------:|---------|
| Positions | 1 (qty 99, SKU-FAILED) | 1 (qty 5, SKU-SUCCESS) | No | **retained** |
| Products | 1 | 1 | No | **retained** |
| Evidence | 1 (`failed.jpg`) | 1 (`success.jpg`) | No | **retained** |
| Raw labels | 1 | 1 | No | **retained** |
| Normalized | 0 | 1 | No | **retained** (failed none) |
| Final counts | 0 | 1 (qty 1) | No | **retained** (failed none) |

---

## 6. Read-Model Consistency

| Consumer | Selection rule | Job resolved | Failed rows visible? | Evidence |
|----------|----------------|--------------|---------------------:|----------|
| `ListAislePositionsUseCase` | `ResultContextResolver` operational | retry job id | No | `CONFIRMED_IN_COMPONENT_TEST` |
| `ExportInventoryCollector` | operational slice | retry job id | No | `CONFIRMED_IN_COMPONENT_TEST` |
| `RecomputeConsolidatedCounts` (`job_scope=retry`) | job-scoped | retry job id | No | `CONFIRMED_IN_COMPONENT_TEST` |
| `RecomputeConsolidatedCounts` (`job_scope="all"`) | all aisle raw | mixed | **Yes** | `CONFIRMED_IN_COMPONENT_TEST` |
| Inventory summary API | — | — | — | `NOT_TESTED` |
| Analytics API | — | — | — | `NOT_TESTED` |

**P2-T003-ALL-SCOPE exact counts:** `success_scope.raw_count == 1`, `all_scope.raw_count == 2`, `all_scope > success_scope`; normalized/final also 2 vs 1.

---

## 7. SQL Server Evidence

| Check | Result |
|-------|--------|
| Isolation guard | Mandatory; skipped in sandbox |
| P2-T001-SQL-POSITIONS | **SKIPPED** |
| SQL-backed layers in test | **positions** (primary claim); products/evidence written via SQL persist but not asserted for duplication |
| Raw/normalized/final in SQL test | **memory-backed** — not SQL evidence |
| Cleanup verification | `verify_sql_scope_fully_removed` (positions, products, evidence, aisle, inventory) in `finally` |

---

## 8. Findings

### WKR-P2-P1-001 — Same-job persist NON_IDEMPOTENT

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Evidence | `CONFIRMED_IN_COMPONENT_TEST` (P2-T001) |
| Category | IDEMPOTENCY |
| Current behavior | Append-only; new UUIDs per map |
| Test | P2-T001 |
| Target block | Phase 2 Part 2 |

### WKR-P2-P1-002 — Changed-report retains stale rows

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Evidence | `CONFIRMED_IN_COMPONENT_TEST` (P2-T002, all layers asserted) |
| Category | DATA_OWNERSHIP |
| Test | P2-T002 |
| Target block | Phase 2 Part 2 |

### WKR-P2-P1-003 — Real failed retry isolated; `job_scope="all"` leaks

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Evidence | `CONFIRMED_IN_COMPONENT_TEST` (P2-T003, P2-T003-ALL-SCOPE) |
| Category | RETRY / READ_MODEL |
| Current behavior | Failed rows retained; operational readers isolated; `all` scope mixes raw/normalized/final |
| Test | P2-T003, P2-T003-ALL-SCOPE |
| Target block | Phase 2 Part 2 |

---

## 9. Recommended Strategy for Phase 2 Part 2

**Primary:** delete-and-replace by `job_id` inside transactional UnitOfWork.  
**Defer:** unique constraints until SQL tests confirm behavior.  
**Follow-on:** deterministic business keys in mapper.

---

## 10. Validation Commands

| Command | Result | Tests | Notes |
|---------|--------|------:|-------|
| `pytest test_worker_phase2_part1_idempotency_*.py` | PASS | 5 pass, 1 skip | Focused Part 1 |
| `pytest test_worker_operational_safety_*.py` | PASS | 18 pass, 2 skip | Phase 1 regression |
| `ruff check` (changed files) | PASS | — | **no auto-fix** |
| Full backend suite | NOT_RUN | — | Use CI / `.venv/bin/python -m pytest` |
| Type check | NOT_RUN | — | Not configured in correction pass |
