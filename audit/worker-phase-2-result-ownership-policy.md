# Worker Phase 2 — Result Ownership and Retry Policy (Proposed)

**Status:** Characterization baseline — **not fully implemented**.  
**Scope:** Phase 2 Part 1 evidence only. No production idempotency fixes in this block.

Legend:

| Tag | Meaning |
|-----|---------|
| **DESIRED_POLICY** | Target invariant for production |
| **CURRENT_BEHAVIOR** | Observed today (memory/component tests unless noted) |
| **PENDING_IMPLEMENTATION** | Requires Phase 2 Part 2+ work |

---

## Rule 1 — Every processing attempt receives a new `job_id`

| | |
|--|--|
| **DESIRED_POLICY** | Retries and re-runs are distinct jobs with distinct `job_id` values. |
| **CURRENT_BEHAVIOR** | `RetryAisleJobUseCase` creates a new job; worker executes under that id. Confirmed in Phase 1 T012 and P2-T003. |
| **Gap** | Manual re-invocation of persist with the same `job_id` is possible (no guard). |
| **Test** | P2-T003 (`job-failed` vs `job-success`); Phase 1 T012 |
| **Block** | Part 2 — optional persist guard / worker contract |

---

## Rule 2 — All job-produced domain results remain attributable to the creating `job_id`

| | |
|--|--|
| **DESIRED_POLICY** | Positions, products, evidence, raw/normalized/final labels carry the job that created them. |
| **CURRENT_BEHAVIOR** | Mapper stamps `job_id` on positions and raw labels; child rows inherit via `position_id`. P2-T003 confirms failed rows stay on `job-failed`, success on `job-success`. |
| **Gap** | No DB unique constraints enforcing ownership; duplicate rows share the same `job_id`. |
| **Test** | P2-T001, P2-T003; helpers `*_for_job()` |
| **Block** | Part 2 — schema constraints + delete/replace by job scope |

---

## Rule 3 — Only a SUCCEEDED job may become the operational result for an aisle

| | |
|--|--|
| **DESIRED_POLICY** | `operational_job_id` points only to a terminal-success `process_aisle` job. |
| **CURRENT_BEHAVIOR** | `V3JobExecutionStateService.mark_success` sets `operational_job_id` for **PRODUCTION** inventories only. Failed jobs do not promote (P2-T003). |
| **Gap** | No compare-and-set; last successful writer wins. Failed job could theoretically be set if caller bypasses state service. |
| **Test** | P2-T003 (`operational_job_id == job-success`) |
| **Block** | Part 2 — operational promotion guard |

---

## Rule 4 — Results from FAILED or CANCELED jobs must never appear in operational UI, exports, summaries, or totals

| | |
|--|--|
| **DESIRED_POLICY** | Operational readers filter by `operational_job_id` / explicit job slice. |
| **CURRENT_BEHAVIOR** | `ResultContextResolver` → `ListAislePositionsUseCase` and `ExportInventoryCollector` return only the operational slice (P2-T003: qty 5, not 99). |
| **Gap** | `RecomputeConsolidatedCounts` with `job_scope="all"` mixes every attempt; analytics paths may count all runs (not covered in Part 1 tests). Failed rows **remain in DB** and are visible if a consumer uses `job_scope="all"` or aisle-wide listing without resolver. |
| **Test** | P2-T003 (positions list + export); aggregate `job_scope="all"` characterized as **NOT_JOB_SCOPED** |
| **Block** | Part 2 — read-model unification; Part 3 — analytics alignment |

---

## Rule 5 — Re-executing persistence for the same `job_id` must be idempotent

| | |
|--|--|
| **DESIRED_POLICY** | Second identical persist produces no net new business rows. |
| **CURRENT_BEHAVIOR** | **NON_IDEMPOTENT**. P2-T001: positions 2→4; duplicate `entity_uid` per job; raw labels append (2→4); normalized/final rebuilt from all raw (4 rows, duplicate SKUs). No delete-before-insert. |
| **Gap** | `v3_report_mapper` assigns new UUIDs per entity on every map (`uuid4()`). Insert-only persist loop. |
| **Test** | P2-T001; P2-T001-SQL (`PENDING_SQL_VERIFICATION`) |
| **Block** | **Part 2** — primary implementation target |

---

## Rule 6 — A successful retry using a new `job_id` must not mix its rows with the previous failed attempt

| | |
|--|--|
| **DESIRED_POLICY** | Operational consumers see only the success job; historical failed rows are non-operational. |
| **CURRENT_BEHAVIOR** | Row isolation by `job_id` works at persistence layer. Operational readers resolve `job-success` only (P2-T003). |
| **Gap** | Failed partial rows retained indefinitely; `job_scope="all"` recompute sees both attempts. |
| **Test** | P2-T003 |
| **Block** | Part 2 — explicit cleanup; Part 2 — recompute default scope |

---

## Rule 7 — Historical results may be retained but must remain non-operational unless explicitly selected for audit

| | |
|--|--|
| **DESIRED_POLICY** | Audit/history views may pass explicit `job_id`; default views use operational slice. |
| **CURRENT_BEHAVIOR** | Failed rows retained (P2-T003: 1 position on `job-failed`). Explicit `job_id` supported by `ResultContextResolver`. |
| **Gap** | No first-class “audit history” API in Part 1 scope. |
| **Test** | P2-T003 (retention); resolver unit behavior (existing) |
| **Block** | Later — audit UI/API |

---

## Rule 8 — Cleanup of failed partial results must be explicit and must not delete the operational job

| | |
|--|--|
| **DESIRED_POLICY** | Cleanup is a deliberate, job-scoped operation with operational-job protection. |
| **CURRENT_BEHAVIOR** | **No automatic cleanup**. Failed partial rows **retained** (P2-T003). |
| **Gap** | No delete-by-job use case or worker hook. |
| **Test** | P2-T003 (cleanup classification: **retained**) |
| **Block** | **Part 2** — explicit cleanup use case |

---

## Rule 9 — Read models must resolve the same operational job consistently

| | |
|--|--|
| **DESIRED_POLICY** | All operational consumers use `ResultContextResolver` (or equivalent) and agree on `job_id_for_slice`. |
| **CURRENT_BEHAVIOR** | Positions list and export agree on `job-success` in P2-T003. |
| **Gap** | Recompute default in persist uses concrete `job_id` (good); ad-hoc `job_scope="all"` does not. Analytics not tested in Part 1. |
| **Test** | P2-T003 (`ListAislePositionsUseCase`, `ExportInventoryCollector`) |
| **Block** | Part 2 — consumer audit; Part 3 — analytics |

---

## Rule 10 — Aggregate layers must not combine multiple job attempts

| | |
|--|--|
| **DESIRED_POLICY** | Totals and exports for operational views use a single job slice. |
| **CURRENT_BEHAVIOR** | Export operational slice: **ISOLATED** (P2-T003). `RecomputeConsolidatedCounts` with `job_scope="all"`: **NOT_JOB_SCOPED** — raw count includes all attempts. |
| **Gap** | Consolidation layer can aggregate cross-job when scope is `"all"`. |
| **Test** | P2-T003 (`job_scope` success vs `"all"`) |
| **Block** | Part 2 — default recompute scope; Part 3 — analytics |

---

## Memory vs SQL evidence

| Area | Memory / component | SQL Server |
|------|-------------------|------------|
| Same-job duplicate persist | `CONFIRMED_IN_COMPONENT_TEST` (P2-T001) | `PENDING_SQL_VERIFICATION` (P2-T001-SQL skipped) |
| Changed-report same job | `CONFIRMED_IN_COMPONENT_TEST` (P2-T002) | Not tested |
| Retry isolation | `CONFIRMED_IN_COMPONENT_TEST` (P2-T003) | Not tested |
| Operational read isolation | `CONFIRMED_IN_COMPONENT_TEST` (P2-T003) | Not tested |

Do not infer SQL uniqueness or transaction boundaries from memory repositories alone.
