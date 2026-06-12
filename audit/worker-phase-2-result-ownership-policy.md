# Worker Phase 2 — Result Ownership and Retry Policy (Proposed)

**Status:** Characterization baseline — **not fully implemented**.

Legend: **DESIRED_POLICY** | **CURRENT_BEHAVIOR** | **PENDING_IMPLEMENTATION**

Evidence labels: `CONFIRMED_IN_COMPONENT_TEST` | `CONFIRMED_IN_SQL_SERVER` | `INFERRED_FROM_CODE` | `NOT_ASSERTED` | `NOT_TESTED` | `PENDING_SQL_VERIFICATION`

---

## Rule 1 — Every processing attempt receives a new `job_id`

| | |
|--|--|
| **DESIRED_POLICY** | Retries are distinct jobs. |
| **CURRENT_BEHAVIOR** | `RetryAisleJobUseCase` creates new UUID job with `retry_of_job_id` lineage. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | Direct re-persist with same `job_id` still possible. |
| **Test** | P2-T003 |
| **Block** | Part 2 optional guard |

---

## Rule 2 — Results attributable to creating `job_id`

| | |
|--|--|
| **DESIRED_POLICY** | All domain rows stamped with creating job. |
| **CURRENT_BEHAVIOR** | Rows scoped by `job_id`; cross-job ID sets do not overlap. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | No DB uniqueness on business keys. |
| **Test** | P2-T003 `assert_no_row_id_overlap` |
| **Block** | Part 2 |

---

## Rule 3 — Only SUCCEEDED job becomes operational

| | |
|--|--|
| **DESIRED_POLICY** | `operational_job_id` → success job only. |
| **CURRENT_BEHAVIOR** | Executor `mark_success` on PRODUCTION inventory sets pointer to retry job. Failed job never operational. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | No compare-and-set (`INFERRED_FROM_CODE`). |
| **Test** | P2-T003 |
| **Block** | Part 2 |

---

## Rule 4 — FAILED/CANCELED rows not in operational UI

| | |
|--|--|
| **DESIRED_POLICY** | Operational consumers filter by operational job. |
| **CURRENT_BEHAVIOR** | Positions list + export return success slice only (SKU-SUCCESS qty 5, not SKU-FAILED 99). **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | `job_scope="all"` includes failed raw/normalized/final. Analytics/inventory summary `NOT_TESTED`. |
| **Test** | P2-T003, P2-T003-ALL-SCOPE |
| **Block** | Part 2–3 |

---

## Rule 5 — Same `job_id` re-persist idempotent

| | |
|--|--|
| **DESIRED_POLICY** | No net new rows on identical re-persist. |
| **CURRENT_BEHAVIOR** | **NON_IDEMPOTENT** — structural position dup + semantic SKU repetition. **Evidence:** P2-T001 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | UUID per entity in mapper (`INFERRED_FROM_CODE`). |
| **Test** | P2-T001; SQL positions `PENDING_SQL_VERIFICATION` |
| **Block** | **Part 2** |

---

## Rule 6 — Successful retry does not mix with failed attempt

| | |
|--|--|
| **DESIRED_POLICY** | Operational slice = success job only. |
| **CURRENT_BEHAVIOR** | Isolated by `job_id` at persistence; operational readers use retry job. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | Failed rows retained; `all` scope mixes (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Test** | P2-T003, P2-T003-ALL-SCOPE |
| **Block** | Part 2 cleanup + scope defaults |

---

## Rule 7 — Historical results retained, non-operational

| | |
|--|--|
| **DESIRED_POLICY** | Audit via explicit `job_id`. |
| **CURRENT_BEHAVIOR** | Failed rows remain in DB. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | No audit API (`NOT_TESTED`). |
| **Test** | P2-T003 |
| **Block** | Later |

---

## Rule 8 — Cleanup explicit, protects operational job

| | |
|--|--|
| **DESIRED_POLICY** | Deliberate job-scoped cleanup. |
| **CURRENT_BEHAVIOR** | No automatic cleanup; failed rows **retained**. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Test** | P2-T003 |
| **Block** | Part 2 |

---

## Rule 9 — Read models resolve operational job consistently

| | |
|--|--|
| **DESIRED_POLICY** | Same `job_id_for_slice` across operational consumers. |
| **CURRENT_BEHAVIOR** | List + export agree on retry job. **Evidence:** P2-T003 (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Gap** | Inventory summary, analytics `NOT_TESTED`. |
| **Test** | P2-T003 |
| **Block** | Part 2–3 |

---

## Rule 10 — Aggregates must not combine attempts (operational views)

| | |
|--|--|
| **DESIRED_POLICY** | Operational totals use single job slice. |
| **CURRENT_BEHAVIOR** | Export isolated; `job_scope="all"` recompute aggregates failed+success raw (2 vs 1). **Evidence:** P2-T003-ALL-SCOPE (`CONFIRMED_IN_COMPONENT_TEST`). |
| **Test** | P2-T003-ALL-SCOPE |
| **Block** | Part 2 |

---

## Duplicate detection conventions (tests)

| Layer | Structural key | Semantic repetition key |
|-------|----------------|-------------------------|
| Position | `job_id + entity_uid` | — |
| Product | `job_id + position_id + sku` | `repeated_products_by_job_sku` |
| Evidence | `job_id + position_id + path` | `repeated_evidence_by_job_path` |
| Raw label | `job_id + position_id + group_key + source_reference` | `repeated_raw_labels_by_source_reference` |
| Normalized | `job_id + position_id + group_key + canonical_sku` | `repeated_normalized_labels_by_job_sku` |
| Final count | `job_id + position_id + sku` | `repeated_final_counts_by_job_sku` |

Helpers live under `tests/support/worker_phase2/duplicate_detection.py`.

---

## Memory vs SQL

| Claim | Level |
|-------|-------|
| Same-job position duplication | `CONFIRMED_IN_COMPONENT_TEST`; SQL `PENDING_SQL_VERIFICATION` |
| Products/evidence on changed report | `CONFIRMED_IN_COMPONENT_TEST` |
| Real failed retry flow | `CONFIRMED_IN_COMPONENT_TEST` |
| `job_scope="all"` leakage | `CONFIRMED_IN_COMPONENT_TEST` |
| SQL raw/normalized/final | `NOT_ASSERTED` (memory repos in SQL test) |
