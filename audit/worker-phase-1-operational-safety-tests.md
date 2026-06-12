# Worker Phase 1 — Operational Safety Tests Report

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Verdict** | `PHASE_1_COMPLETE_WITH_GAPS` |
| **Tests added** | 18 (17 component/unit + 1 optional SQL integration) |
| **Tests passing** | 17/17 component (SQL integration skipped when DB unavailable) |
| **Production files modified** | 0 |
| **SQL Server integration** | Optional test present; skipped in environments without configured/reachable SQL |

Phase 1 adds deterministic characterization tests for the highest-risk worker failure scenarios identified in the read-only audit. No production behavior was changed. Memory/component tests confirm partial persistence, partial finalization, cancellation checkpoints, retry isolation, provider multimodal rejection, and image traceability.

**Remaining gap:** SQL integration test requires isolated test DB with migrations applied; not executed in this CI run.

---

## 2. Test Inventory

| Test ID | File | Test name | Type | Scenario | Result |
|---------|------|-----------|------|----------|--------|
| WKR-P1-T001 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t001_persist_fails_on_second_position_leaves_first_entity_committed` | COMPONENT | Mid-persist failure | PASS |
| WKR-P1-T007 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t007_recompute_failure_after_entity_persist_marks_job_failed` | COMPONENT | Recompute failure after persist | PASS |
| WKR-P1-T012 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t012_retry_isolates_job_scoped_results_safe_with_conditions` | COMPONENT | Retry job isolation | PASS |
| WKR-P1-T002 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t002_artifact_failure_after_persist_leaves_domain_rows_failed_job` | COMPONENT | Artifact fail after persist | PASS |
| WKR-P1-T003A | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_a_mark_success_job_save_fails_after_artifacts` | COMPONENT | mark_success job save fail | PASS |
| WKR-P1-T003B | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_b_aisle_save_fails_after_job_would_succeed` | COMPONENT | mark_success aisle save fail | PASS |
| WKR-P1-T003C | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_c_inventory_reconcile_fails_after_terminal_writes` | COMPONENT | reconcile fail after success writes | PASS |
| WKR-P1-T004 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t004_cancel_requested_before_executor_skips_pipeline_and_aisle_stays_queued` | COMPONENT | Cancel before executor | PASS |
| WKR-P1-T005 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t005_cancel_before_provider_checkpoint_skips_persist` | COMPONENT | Cancel pre-provider | PASS |
| WKR-P1-T006 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t006_cancel_after_provider_before_persist_skips_domain_writes` | COMPONENT | Cancel post-provider | PASS |
| WKR-P1-T006B | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t006b_cancel_after_persist_stops_before_artifacts_not_mark_success` | COMPONENT | Cancel after persist | PASS |
| WKR-P1-T008 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t008_deepseek_rejects_multimodal_at_adapter_execute` | UNIT | DeepSeek multimodal block | PASS |
| WKR-P1-T009 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t009_below_frame_cap_manifest_matches_sent_ids` | UNIT | Below frame cap | PASS |
| WKR-P1-T010 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t010_above_frame_cap_truncates_deterministically` | UNIT | Above frame cap | PASS |
| WKR-P1-T010B | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t010b_provider_adapters_preserve_primary_frame_ref_order` | UNIT | Adapter ordering | PASS |
| WKR-P1-T011 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t011_reference_images_labeled_separate_from_primary_evidence` | UNIT | Reference separation | PASS |
| WKR-P1-T013 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t013_source_image_id_preserved_through_persist_and_read_model` | COMPONENT | E2E source_image_id | PASS |
| WKR-P1-T001-SQL | `test_worker_operational_safety_sql_integration.py` | `test_wkr_p1_t001_sql_partial_persist_characterization` | INTEGRATION | SQL partial persist | SKIP (no SQL) |

---

## 3. Scenario Outcome Matrix

| Scenario | Job | Aisle | Inventory | Domain data | Artifacts | Retry | Classification |
|----------|-----|-------|-----------|-------------|-----------|-------|----------------|
| T001 mid-persist fail | FAILED | FAILED | FAILED | 1/2 entities committed | Not reached | New job succeeds | PARTIAL_NON_ATOMIC |
| T007 recompute fail | FAILED | FAILED | FAILED | Entities committed | Not reached | — | STALE_AGGREGATES |
| T012 retry | job2 SUCCEEDED | PROCESSED | — | job1 partial + job2 full | job2 yes | SAFE_WITH_CONDITIONS | Isolated by job_id |
| T002 artifact fail | FAILED | FAILED | FAILED | Committed | None in result_json | New job needed | PARTIAL_FINALIZATION |
| T003A job save fail | FAILED | FAILED | — | Committed | Uploaded | — | PARTIAL_FINALIZATION |
| T003B aisle save fail | FAILED | not PROCESSED | — | Committed | Uploaded | — | SPLIT_TERMINAL_RISK |
| T003C reconcile fail | FAILED | — | — | Committed | Uploaded | — | PARTIAL_FINALIZATION |
| T004 early cancel | CANCELED | **QUEUED** | — | None | None | — | AISLE_NOT_RECONCILED |
| T005 pre-provider cancel | CANCELED | FAILED/CANCELED | — | None | None | — | COOPERATIVE |
| T006 post-provider cancel | CANCELED | FAILED/CANCELED | — | None | None | — | COOPERATIVE |
| T006B post-persist cancel | **FAILED** (not CANCELED) | FAILED | — | Committed | None | — | CANCEL_AS_ARTIFACT_ERROR |
| T008 DeepSeek multimodal | — | — | — | — | — | — | BLOCKED_AT_ADAPTER |

---

## 4. Confirmed Findings

### WKR-P1-IMP-001
- **Title:** PersistAisleResult is non-atomic across entity saves
- **Severity:** CRITICAL | **Status:** CONFIRMED | **Confidence:** HIGH
- **Test evidence:** WKR-P1-T001
- **Current behavior:** Second position save failure leaves first entity triple committed
- **Operational impact:** Partial domain rows on failed jobs
- **Recommendation:** Phase 2 transactional unit-of-work
- **Target phase:** 2

### WKR-P1-IMP-002
- **Title:** Artifact failure after persist leaves committed domain data
- **Severity:** CRITICAL | **Status:** CONFIRMED | **Confidence:** HIGH
- **Test evidence:** WKR-P1-T002
- **Recommendation:** Phase 2 artifact recovery / finalize-outbox

### WKR-P1-IMP-003
- **Title:** Early cancel leaves aisle queued while job canceled
- **Severity:** HIGH | **Status:** CONFIRMED | **Confidence:** HIGH
- **Test evidence:** WKR-P1-T004
- **Recommendation:** Phase 2 aisle reconciliation on early cancel

### WKR-P1-IMP-004
- **Title:** Post-persist cancellation treated as artifact failure (FAILED not CANCELED)
- **Severity:** MEDIUM | **Status:** CONFIRMED | **Confidence:** HIGH
- **Test evidence:** WKR-P1-T006B
- **Recommendation:** Phase 2 route pre_upload cancel to cancel_job_and_aisle

### WKR-P1-IMP-005
- **Title:** Retry is SAFE_WITH_CONDITIONS — stale partial rows remain for failed job_id
- **Severity:** MEDIUM | **Status:** CONFIRMED | **Confidence:** HIGH
- **Test evidence:** WKR-P1-T012

---

## 5. Retry Safety Classification

| Path | Classification | Notes |
|------|----------------|-------|
| New job after FAILED (full retry) | SAFE_WITH_CONDITIONS | Old job rows remain; operational pointer selects success |
| New job after partial persist fail | SAFE_WITH_CONDITIONS | Partial rows tagged with failed job_id |
| Re-run same job_id | UNSAFE / blocked | Executor rejects non-STARTING |
| Retry after artifact-only failure | SAFE_WITH_CONDITIONS | Domain may exist; artifacts missing |

---

## 6. Testability Changes

| File | Change | Why needed | Behavior changed? |
|------|--------|------------|-------------------|
| — | None | Tests use existing constructor injection and test doubles | No |

---

## 7. Remaining Gaps

- SQL Server integration test not executed (requires `SQLSERVER_*` test config + migrations)
- No live provider executor tests (by design — adapter unit tests only)
- Cancellation during active persist loop not injectable (no checkpoint inside use case)

---

## 8. Recommendation for Phase 2

1. Introduce optional `UnitOfWork` around `PersistAisleResultUseCase` entity loop
2. Add finalize-outbox or artifact-retry path separate from full reprocess
3. Reconcile aisle on early cancel (`cancel_job` → `cancel_job_and_aisle`)
4. Route `PipelineCancellationRequestedError` in artifact block to cooperative cancel handler
5. Cleanup policy for orphaned partial rows on failed job_id
6. Run SQL integration characterization in CI with isolated test DB

---

## 9. Validation Commands

| Command | Result | Notes |
|---------|--------|-------|
| `python3 -m pytest tests/infrastructure/pipeline/test_worker_operational_safety_phase1.py tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py -v --no-cov` | PASS | 17/17 |
| `python3 -m ruff check tests/support/worker_phase1 tests/infrastructure/pipeline/test_worker_operational_safety_*.py` | PASS | After fixes |
| Full backend suite | NOT_RUN | Time budget; focused suite passed |
| SQL integration test | NOT_RUN / SKIP | No SQL in sandbox |
