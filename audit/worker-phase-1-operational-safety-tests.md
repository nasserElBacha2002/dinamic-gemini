# Worker Phase 1 — Operational Safety Tests Report

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Verdict** | `PHASE_1_COMPONENT_COVERAGE_COMPLETE_WITH_INTEGRATION_GAPS` |
| **Tests added** | 19 (18 component/unit + 1 optional SQL integration) |
| **Tests passing** | 18/18 component (focused suite) |
| **Production files modified** | 0 |
| **SQL Server integration** | Safely skipped when isolated test DB / ODBC unavailable |

Phase 1 characterization tests cover partial persistence, partial finalization, cancellation checkpoints, retry isolation, provider multimodal rejection, and image traceability. Corrections strengthened evidentiary value: explicit execution spies, save-attempt history on partial-finalization doubles, connected manifest→payload chains, negative reference-ID traceability, shared persistence repositories on retry, and FK-safe SQL cleanup.

**Remaining gap:** SQL Server partial-persist atomicity is `PENDING_SQL_VERIFICATION` until the integration test runs against an isolated test database with migrations applied.

---

## 2. Evidence Classification

| Finding | Component / memory | SQL Server |
|---------|-------------------|------------|
| WKR-P1-IMP-001 non-atomic persist | `CONFIRMED_IN_COMPONENT_TEST` (T001) | `PENDING_SQL_VERIFICATION` (T001-SQL) |
| WKR-P1-IMP-002 artifact after persist | `CONFIRMED_IN_COMPONENT_TEST` (T002) | — |
| WKR-P1-IMP-003 early cancel aisle queued | `CONFIRMED_IN_COMPONENT_TEST` (T004) | — |
| WKR-P1-IMP-004 post-persist cancel → FAILED | `CONFIRMED_IN_COMPONENT_TEST` (T006B) | — |
| WKR-P1-IMP-005 retry isolation | `CONFIRMED_IN_COMPONENT_TEST` (T012) | — |
| Frame cap manifest↔payload | `CONFIRMED_IN_COMPONENT_TEST` (T010) | — |
| Reference ID as provider source | `CONFIRMED_IN_COMPONENT_TEST` (T011B) | — |
| source_image_id E2E chain | `CONFIRMED_IN_COMPONENT_TEST` (T013) | — |

Do **not** promote SQL atomicity to HIGH confidence until T001-SQL executes successfully with post-test cleanup verification.

---

## 3. Test Inventory

| Test ID | File | Test name | Type | Scenario | Result |
|---------|------|-----------|------|----------|--------|
| WKR-P1-T001 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t001_…` | COMPONENT | Mid-persist failure | PASS |
| WKR-P1-T007 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t007_…` | COMPONENT | Recompute failure after persist | PASS |
| WKR-P1-T012 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t012_…` | COMPONENT | Retry job isolation (shared repos) | PASS |
| WKR-P1-T002 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t002_…` | COMPONENT | Artifact fail after persist | PASS |
| WKR-P1-T003A | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_a_…` | COMPONENT | mark_success job save fail + save history | PASS |
| WKR-P1-T003B | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_b_…` | COMPONENT | mark_success aisle save fail + save history | PASS |
| WKR-P1-T003C | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t003_case_c_…` | COMPONENT | reconcile fail after terminal writes | PASS |
| WKR-P1-T004 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t004_…` | COMPONENT | Cancel before executor + spies | PASS |
| WKR-P1-T005 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t005_…` | COMPONENT | Cancel pre-provider + spies | PASS |
| WKR-P1-T006 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t006_…` | COMPONENT | Cancel post-provider + spies | PASS |
| WKR-P1-T006B | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t006b_…` | COMPONENT | Cancel after persist + spies | PASS |
| WKR-P1-T008 | `test_worker_operational_safety_phase1.py` | `test_wkr_p1_t008_…` | UNIT | DeepSeek multimodal block | PASS |
| WKR-P1-T009 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t009_…` | UNIT | Below frame cap | PASS |
| WKR-P1-T010 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t010_…` | UNIT | Frame cap: acquired == manifest == payload | PASS |
| WKR-P1-T010B | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t010b_…` | UNIT | Adapter ordering | PASS |
| WKR-P1-T011 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t011_…` | UNIT | Reference payload labeling | PASS |
| WKR-P1-T011B | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t011b_…` | COMPONENT | Reference ID returned → TRACEABILITY_INVALID; still persisted | PASS |
| WKR-P1-T013 | `test_worker_operational_safety_traceability_phase1.py` | `test_wkr_p1_t013_…` | COMPONENT | Connected identity chain E2E | PASS |
| WKR-P1-T001-SQL | `test_worker_operational_safety_sql_integration.py` | `test_wkr_p1_t001_sql_…` | INTEGRATION | SQL partial persist + cleanup | SKIP (no isolated SQL) |

---

## 4. Scenario Outcome Matrix

| Scenario | Job | Aisle | Inventory | Domain data | Artifacts | Retry | Classification |
|----------|-----|-------|-----------|-------------|-----------|-------|----------------|
| T001 mid-persist fail | FAILED | FAILED | FAILED | 1/2 entities committed | Not reached | New job succeeds | PARTIAL_NON_ATOMIC |
| T007 recompute fail | FAILED | FAILED | FAILED | Entities committed | Not reached | — | STALE_AGGREGATES |
| T012 retry | job2 SUCCEEDED | PROCESSED | — | job1 partial + job2 full | job2 yes | SAFE_WITH_CONDITIONS | Isolated by job_id |
| T002 artifact fail | FAILED | FAILED | FAILED | Committed | None in result_json | New job needed | PARTIAL_FINALIZATION |
| T003A job save fail | FAILED | FAILED | — | Committed | Uploaded | — | PARTIAL_FINALIZATION |
| T003B aisle save fail | FAILED | FAILED | — | Committed | Uploaded | — | SPLIT_TERMINAL_RISK |
| T003C reconcile fail | FAILED | FAILED | — | Committed | Uploaded | — | PARTIAL_FINALIZATION |
| T004 early cancel | CANCELED | **QUEUED** | PROCESSING | None | None | — | AISLE_NOT_RECONCILED |
| T005 pre-provider cancel | CANCELED | CANCELED | — | None | None | — | COOPERATIVE |
| T006 post-provider cancel | CANCELED | CANCELED | — | None | None | — | COOPERATIVE |
| T006B post-persist cancel | **FAILED** | FAILED | — | Committed | None | — | CANCEL_AS_ARTIFACT_ERROR |
| T011B reference as source | — | — | — | TRACEABILITY_INVALID; persisted with ref ID | — | — | INVALID_BUT_PERSISTED |
| T008 DeepSeek multimodal | — | — | — | — | — | — | BLOCKED_AT_ADAPTER |

---

## 5. Confirmed Findings

### WKR-P1-IMP-001
- **Title:** PersistAisleResult is non-atomic across entity saves
- **Severity:** CRITICAL | **Status:** CONFIRMED (component) | **Confidence:** HIGH (component), PENDING (SQL)
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T001; `PENDING_SQL_VERIFICATION` — WKR-P1-T001-SQL
- **Recommendation:** Phase 2 transactional unit-of-work

### WKR-P1-IMP-002
- **Title:** Artifact failure after persist leaves committed domain data
- **Severity:** CRITICAL | **Status:** CONFIRMED | **Confidence:** HIGH
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T002

### WKR-P1-IMP-003
- **Title:** Early cancel leaves aisle queued while job canceled
- **Severity:** HIGH | **Status:** CONFIRMED | **Confidence:** HIGH
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T004 (uses `cancel_job`, not `cancel_job_and_aisle`)

### WKR-P1-IMP-004
- **Title:** Post-persist cancellation treated as artifact failure (FAILED not CANCELED)
- **Severity:** MEDIUM | **Status:** CONFIRMED | **Confidence:** HIGH
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T006B

### WKR-P1-IMP-005
- **Title:** Retry is SAFE_WITH_CONDITIONS — stale partial rows remain for failed job_id
- **Severity:** MEDIUM | **Status:** CONFIRMED | **Confidence:** HIGH
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T012
- **Note:** Partial-fail job has positions/products/evidence but no raw labels (persist aborts before `save_many`)

### WKR-P1-IMP-006 (new)
- **Title:** Provider returning supplier reference ID is marked TRACEABILITY_INVALID but still persisted
- **Severity:** MEDIUM | **Status:** CONFIRMED | **Confidence:** HIGH
- **Evidence:** `CONFIRMED_IN_COMPONENT_TEST` — WKR-P1-T011B

---

## 6. Test Support Changes (corrections)

| File | Change |
|------|--------|
| `doubles.py` | Save-attempt snapshots on partial-failing repos; `FailingArtifactStore` fail modes (`exact` / `from_onward`); `FixedClock` on cancel injection |
| `executor_harness.py` | Injectable product/evidence/raw/norm/final/source_asset repos |
| `spies.py` | `ExecutionSpy` for persist/recompute/artifacts/mark_success/cancel/fail counts |
| `sql_cleanup.py` | FK-safe scoped DELETE + `assert_sql_integration_database_is_safe()` |

---

## 7. Remaining Gaps

- SQL integration: requires `backend/.env.test` with test-database name + ODBC driver + migrations
- Full backend suite not validated in Python 3.9 sandbox (collection errors on `X | Y` syntax — use Python 3.11+)
- Cancellation during active persist loop not injectable (no checkpoint inside use case)
- T011B: invalid traceability does not block persistence today

---

## 8. Validation Commands

| Command | Result | Tests | Duration | Notes |
|---------|--------|------:|---------:|-------|
| Focused operational safety + traceability | PASS | 18/18 | ~7.4s | `CONFIRMED_IN_COMPONENT_TEST` |
| SQL integration | SKIPPED_NO_ISOLATED_SQL | 0/1 | ~6.5s | No ODBC / test DB in sandbox |
| Full backend suite | PRE_EXISTING_FAILURE | — | — | Python 3.9 collection errors (unrelated) |
| Ruff (changed files) | PASS | — | — | |
| Mypy | NOT_RUN | — | — | |
| Architecture checks | NOT_RUN | — | — | |

---

## 9. Recommendation for Phase 2

1. Introduce optional `UnitOfWork` around `PersistAisleResultUseCase` entity loop
2. Run T001-SQL in CI with isolated test DB; verify cleanup repeatability
3. Reconcile aisle on early cancel (`cancel_job` → include aisle)
4. Block or flag persistence when `TRACEABILITY_INVALID`
5. Cleanup policy for orphaned partial rows on failed job_id
