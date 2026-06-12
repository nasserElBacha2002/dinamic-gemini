# Worker Phase 2 Part 1 — Idempotency Characterization Report

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Verdict** | `PART_1_COMPLETE_WITH_SQL_GAPS` |
| **Tests added** | 4 (3 component + 1 optional SQL) |
| **Memory/component results** | 3/3 PASS |
| **SQL Server status** | P2-T001-SQL **SKIPPED** (no isolated test DB / ODBC in CI sandbox) |
| **Same-job idempotency** | **NON_IDEMPOTENT** (all layers append or rebuild from accumulated raw) |
| **Changed-report behavior** | **APPEND_ONLY** / **PARTIAL_REPLACEMENT** (stale rows retained) |
| **Retry isolation** | **ISOLATED_BY_JOB_ID** at persistence; operational readers **ISOLATED** |
| **Read-model leakage** | Positions list and export **ISOLATED**; `job_scope="all"` recompute **LEAKS** |
| **Recommended Part 2 strategy** | **Delete-and-replace by job scope** inside a **transactional UnitOfWork**, plus **deterministic business keys**; defer broad unique constraints until scope delete is proven |

**Production files modified:** 0  
**Test/support files added/extended:** harness helpers, duplicate detection, job-scope inspection, characterization tests, optional SQL test.

---

## 2. Test Inventory

| Test ID | Test | Type | Result | Evidence level |
|---------|------|------|--------|----------------|
| P2-T001 | `test_p2_t001_same_job_identical_persist_is_non_idempotent` | COMPONENT | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T002 | `test_p2_t002_same_job_changed_report_appends_stale_and_new_rows` | COMPONENT | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T003 | `test_p2_t003_partial_fail_then_success_retry_isolates_by_job_id` | COMPONENT | PASS | `CONFIRMED_IN_COMPONENT_TEST` |
| P2-T001-SQL | `test_p2_t001_sql_same_job_identical_persist_duplicates_rows` | INTEGRATION | SKIP | `PENDING_SQL_VERIFICATION` |

**Regression:** Phase 1 operational safety suite — 18 passed, 2 skipped (unchanged).

---

## 3. Same-Job Idempotency Matrix (P2-T001)

| Layer | First run rows | Second run rows | Duplicates | Classification |
|-------|---------------:|----------------:|------------|----------------|
| Positions | 2 | 4 | `entity_uid` ×2 per entity | **NON_IDEMPOTENT** (append) |
| Products | 2 | 4 | SKU ×2 per job | **NON_IDEMPOTENT** (append) |
| Evidence | 2 | 4 | path ×2 per job | **NON_IDEMPOTENT** (append) |
| Raw labels | 2 | 4 | `source_reference` (entity) ×2 | **APPEND_ONLY** |
| Normalized labels | 2 | 4 | SKU ×2 (rebuild from all raw) | **PARTIAL_REPLACEMENT** (scope replace then insert from accumulated raw) |
| Final counts | 2 | 4 | SKU ×2 (same as normalized) | **PARTIAL_REPLACEMENT** |

**Notes:** Second run retains first-run position IDs (overlap 2) and adds 2 new UUID rows. Mapper generates fresh `uuid4()` per entity (`v3_report_mapper.py`). No exception on second execution.

---

## 4. Changed-Report Behavior (P2-T002)

Setup: run1 = entities A+B; run2 same `job_id` = A′ (qty 99), B removed, C added.

| Layer | Updated | Duplicated | Stale rows retained | Classification |
|-------|--------:|-----------:|--------------------:|----------------|
| Positions | 0 in-place | A ×2 | B ×1 (stale qty 4) | **APPEND_ONLY** |
| Products | 0 in-place | per new positions | stale products on old B position | **APPEND_ONLY** |
| Evidence | 0 in-place | per new positions | stale evidence | **APPEND_ONLY** |
| Raw labels | 0 in-place | A ×2 | B ×1, C ×1 | **APPEND_ONLY** |
| Normalized | rebuild | A ×2 SKUs | B, C present | **PARTIAL_REPLACEMENT** |
| Final counts | rebuild | A ×2 SKUs | B, C present | **PARTIAL_REPLACEMENT** |

**Read model:** Would expose all 4 positions for the job if queried by `job_id` without operational filter — mixed stale and new quantities.

---

## 5. Retry Isolation Matrix (P2-T003)

| Layer | Failed-job rows | Successful-job rows | Mixed operationally? | Cleanup |
|-------|----------------:|------------------:|---------------------:|---------|
| Positions | 1 (qty 99) | 2 (qty 5) | No | **retained** |
| Products | 1 | 2 | No | **retained** |
| Evidence | 1 | 2 | No | **retained** |
| Raw labels | 0 (persist aborted before raw save) | ≥1 | No | **retained** (N/A for failed) |
| Normalized / final | 0 | ≥1 | No | **retained** |

`aisle.operational_job_id == job-success` after `mark_success`.

---

## 6. Read-Model Consistency (P2-T003)

| Consumer | Selection rule | Job resolved | Failed rows visible? |
|----------|----------------|--------------|---------------------:|
| `ListAislePositionsUseCase` | `ResultContextResolver` → operational | `job-success` | No |
| `ExportInventoryCollector` | same resolver | `job-success` | No |
| `RecomputeConsolidatedCounts` (`job_scope="all"`) | all rows in aisle | mixed | **Yes** (raw_count ≥ success-only) |
| Inventory summary API | — | — | **NOT_TESTED** |
| Analytics API | — | — | **NOT_TESTED** |

---

## 7. SQL Server Evidence

| Check | Result |
|-------|--------|
| Database isolation check | `assert_sql_integration_database_is_safe()` — not satisfied in dev sandbox |
| Test execution | **SKIPPED** |
| Cleanup verification | N/A |
| Repeated-run repeatability | N/A |
| Pending gaps | P2-T001-SQL; full-layer SQL characterization; constraint verification |

---

## 8. Findings

### WKR-P2-P1-001 — Same-job persist is NON_IDEMPOTENT

| Field | Value |
|-------|-------|
| **Severity** | HIGH |
| **Status** | OPEN |
| **Evidence** | `CONFIRMED_IN_COMPONENT_TEST` |
| **Category** | IDEMPOTENCY |
| **Current behavior** | Identical second persist doubles rows; new UUIDs per map. |
| **Expected invariant** | Rule 5 — idempotent re-persist for same `job_id`. |
| **Operational impact** | Duplicate positions/labels if worker or API retries persist without new job. |
| **Files** | `persist_aisle_result.py`, `v3_report_mapper.py` |
| **Schema** | No unique index on `(job_id, entity_uid)` |
| **Test** | P2-T001 |
| **Recommended correction** | Job-scoped delete-and-replace before insert; deterministic IDs optional |
| **Target block** | Phase 2 Part 2 |

### WKR-P2-P1-002 — Changed-report same job retains stale rows

| Field | Value |
|-------|-------|
| **Severity** | HIGH |
| **Status** | OPEN |
| **Evidence** | `CONFIRMED_IN_COMPONENT_TEST` |
| **Category** | DATA_OWNERSHIP |
| **Current behavior** | Append-only positions/products/evidence; entity B remains after removal from report. |
| **Expected invariant** | Job slice reflects latest report snapshot. |
| **Operational impact** | Stale entities in job-scoped queries; inflated counts with `job_scope="all"`. |
| **Files** | `persist_aisle_result.py` |
| **Test** | P2-T002 |
| **Recommended correction** | Replace-all-by-`job_id` transactional persist |
| **Target block** | Phase 2 Part 2 |

### WKR-P2-P1-003 — Failed partial rows retained; operational readers isolated

| Field | Value |
|-------|-------|
| **Severity** | MEDIUM |
| **Status** | OPEN (retention); MITIGATED (operational reads) |
| **Evidence** | `CONFIRMED_IN_COMPONENT_TEST` |
| **Category** | RETRY / READ_MODEL |
| **Current behavior** | Failed job rows stay in DB; export/positions use operational job only. |
| **Expected invariant** | Rules 4, 6, 8. |
| **Operational impact** | DB growth; leakage only if consumer bypasses resolver or uses `job_scope="all"`. |
| **Files** | `v3_job_execution_state.py`, `result_context_resolver.py`, `recompute_consolidated_counts.py` |
| **Test** | P2-T003 |
| **Recommended correction** | Explicit failed-job cleanup + tighten default recompute scope |
| **Target block** | Phase 2 Part 2 |

---

## 9. Recommended Strategy for Phase 2 Part 2

| Option | Benefits | Risks | Compatibility | Migration | Test impact |
|--------|----------|-------|---------------|-----------|-------------|
| **Deterministic IDs** | Stable keys; simpler upsert | Mapper complexity; collision handling | Medium — mapper change | Low | Update golden IDs in tests |
| **Unique constraints** | DB-enforced safety | Hard fail on current append behavior; needs cleanup first | Low until idempotent write | Medium — new indexes | SQL integration required |
| **Upsert by business key** | Partial updates | Complex per-layer keys; stale row deletion for removed entities | Medium | Low | Many characterization tests |
| **Delete-and-replace by job scope** | Matches desired snapshot semantics; clears stale entities | Must not delete other jobs; needs transaction | **High** | Low (no schema required for MVP) | P2-T001/T002 should flip to PASS |
| **Transactional UnitOfWork** | Atomic persist + recompute | New abstraction; SQL + memory parity | **Required** for production safety | Low | New integration tests |

**Recommendation:** Implement **delete-and-replace by `job_id`** inside a **transactional UnitOfWork** as the primary Part 2 deliverable. Add **deterministic business keys** in the mapper as a follow-on hardening step. Defer **unique constraints** until SQL tests confirm delete-replace behavior and cleanup paths protect `operational_job_id`.

---

## 10. Validation Commands

| Command | Result | Tests | Duration | Notes |
|---------|--------|------:|---------:|-------|
| `pytest test_worker_phase2_part1_idempotency_*.py` | PASS | 3 pass, 1 skip | ~3s | Focused Part 1 |
| `pytest test_worker_operational_safety_*.py` | PASS | 18 pass, 2 skip | ~4s | Phase 1 regression |
| `ruff check` (changed files) | PASS | — | <1s | After `--fix` |
| Full backend suite | NOT_RUN | — | — | Deferred; use `.venv/bin/python -m pytest` in CI |
