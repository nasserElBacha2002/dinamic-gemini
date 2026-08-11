# DB integrity — final architecture (Phases 0–6)

**Canonical close-out document.** Prefer this over per-phase notes when deciding future persistence changes.
**Date:** 2026-08-11
**Migration HEAD (verified):** `0095`
**Phase 6 status:** see `audit/db-integrity-final-validation.md`

---

## Executive summary

Phases 0–6 established a clear ownership model for SQL Server persistence integrity without application Stored Procedures or Triggers:

| Mechanism | Role |
| --------- | ---- |
| UNIQUE / filtered UNIQUE / CHECK / FK | Final integrity & idempotency authority |
| Explicit transactions | Multi-write atomicity |
| Optimistic CAS (`compare_and_set_status`) | Concurrent derived-state updates |
| `InventoryStatusReconciler` | Detect + repair derived inventory status |
| Set-based / batched SQL | Throughput without widening TX scope |
| Application SP | **None** (Phase 4: no measured ROI) |
| Triggers | **None** (Phase 5: all candidates failed A–I) |

Phase 6 closed the `completed_at` follow-up as **NO_ACTION** for a DB CHECK (application + reconciler remain authority), aligned domain `mark_*` helpers with reconciler semantics, and published this architecture + validation evidence.

---

## Final phase status

| Phase | Objective | Production changes | DB changes | Tests | Final decision |
| ----- | --------- | ------------------ | ---------- | ----- | -------------- |
| 0 | Integrity baseline / critical unique indexes | Catalog assertions; migration authority | HEAD `0095`; no new SP/Trigger | `db_integrity`, D1 concurrency | **COMPLETE** |
| 1 | Package/CSV confirm TX boundaries | PLAN→STAGE→APPLY; shared cursor; one APPLY commit | None | SQL package TX suite | **COMPLETE** |
| 2 | Batching / set-based CSV | `sql_batch`, chunked IN/VALUES, scoped `fast_executemany` | None (indexes from 0094 already) | local CSV unit + SQL batch | **COMPLETE** |
| 3 | Derived inventory status reconciliation | Pure derive + CAS + verify-after-write + outcomes | Port: abstract CAS | unit + SQL drift/concurrency | **COMPLETE** |
| 4 | Stored Procedure evaluation | Docs only | 0 app SPs | Catalog queries | **NO_ACTION_REQUIRED** |
| 5 | Trigger evaluation | Docs only | 0 triggers | Catalog queries | **NO_ACTION_REQUIRED** |
| 6 | Cleanup, architecture, validation | Domain `completed_at` clear on leave COMPLETED; docs | **0 new migrations** | Domain + full integrity suites | **COMPLETE** (see validation) |

---

## Architecture before

```text
Mixed assumptions:
- Some uniqueness only in app paths
- Package confirm risked multi-commit / long locks with storage
- Inventory status treated as writable workflow state in places
- No formal detect vs repair / CAS contract
- Unclear SP/Trigger policy
```

---

## Architecture after

```text
API / use cases
  → domain (workflow rules, pure derive)
  → repositories (TX orchestration, CAS, batching)
  → SQL Server (constraints = final integrity authority)
```

For critical operations:

```text
constraints / unique indexes  = final integrity & idempotency authority
transactions                  = atomic multi-write authority
CAS                           = optimistic concurrency primitive
reconciler                    = derived-state recovery (not SoT for aisles)
```

```text
constraints = integrity.
transactions = atomicity.
unique indexes = idempotency / uniqueness.
CAS = optimistic concurrency.
backend domain = workflow and business rules.
reconciliation = recoverable derived state.
stored procedures = only with measured ROI.
triggers = only when unavoidable (A–I).
```

---

## Invariant ownership

| Invariant | DB mechanism | Application mechanism | Authority |
| --------- | ------------ | --------------------- | --------- |
| Upload idempotency | `UQ_source_assets_aisle_upload_batch_client` (0044) | Upload use cases catch unique violation | **SQL Server** |
| External request idempotency | `UQ_eiar_idempotency_key` (0056) | External analysis enqueue | **SQL Server** |
| Ordered capture uniqueness | `UQ_source_assets_ordered_session_*` (0074) | Ordered capture writers | **SQL Server** |
| Manual override uniqueness / idempotency | `UQ_manual_position_override_active`, `UQ_manual_position_override_idempotency` (0084) | Override use cases | **SQL Server** |
| Local CSV productive label uniqueness | `UX_local_csv_productive_label` (+ import-row UQ) (0094) | Confirm writers + revalidation | **SQL Server** |
| Counted product label uniqueness | `UQ_icpl_aisle_label` (0095; inventory-scoped UQ removed) | Label claim paths | **SQL Server** |
| Inventory status projection | Persisted column only | Pure derive + reconciler CAS | **Backend derive**; DB holds projection |
| `COMPLETED` ↔ `completed_at` | No CHECK (Phase 6 NO_ACTION) | Reconciler CAS + metadata repair; domain `mark_*` clears on leave | **Backend** |
| Package confirm atomicity | TX + row locks | `SqlLocalInventoryPackageRepository` PLAN/APPLY | **Backend TX** + status gates |
| CSV confirm atomicity | Same APPLY TX (package) or standalone CSV TX | Writer + shared cursor | **Backend TX** + unique indexes |
| Job claims | Unique / CAS-style updates as designed | Worker claim paths | **Backend TX** + DB uniqueness where present |

Avoid dual ownership: if SQL UNIQUE exists, application must treat violation as the race winner signal — not a parallel soft check that “also wins.”

---

## Transaction boundaries

| Flow | Transaction owner | Locks | Commit count | Idempotency authority |
| ---- | ----------------- | ----- | ------------ | --------------------- |
| Package confirm (two-phase) | `SqlLocalInventoryPackageRepository` | UPDLOCK package→CSV on PLAN (rolled back) and APPLY | 1 APPLY commit (PLAN rolls back); idempotent CONFIRMED may commit short read | Unique productive indexes + status |
| Package confirm (single-phase) | Same | UPDLOCK on confirm path | 1 | Same |
| CSV confirm standalone | CSV confirm use case / repo | Import row lock as designed | 1 | Unique indexes |
| Job STARTING→RUNNING | Job repository / worker | Claim update | 1 per transition | Job claim uniqueness / CAS |
| Worker claim | Job repo | Claim row | 1 | Claim token / status |
| Outbox claim | Outbox worker | Claim update | 1 | Outbox claim semantics |
| Counted label claim | Label repo | Insert + unique | 1 | `UQ_icpl_aisle_label` |
| Inventory reconciliation | Reconciler → `compare_and_set_status` | Row UPDATE WHERE status=expected | 1 per CAS attempt | CAS + verify-after-write |

### Package confirm (must remain)

```text
optimistic gate
→ PLAN TX
→ rollback/release locks
→ STAGE storage outside SQL locks
→ APPLY TX
→ one commit
→ post-commit materialization
```

Productive rows, CSV `CONFIRMED`, and package `CONFIRMED` stay in **one APPLY transaction**.

### CSV confirm

- Standalone: one transaction.
- Inside package: shared cursor / same APPLY TX.
- No unexpected internal commits.
- Secondary/label uniqueness revalidated under lock; UNIQUE indexes are authority.

---

## Concurrency model

- **Optimistic:** inventory status CAS; package re-confirm races resolved by status + uniques.
- **Pessimistic (short):** UPDLOCK during PLAN/APPLY for package rows — never hold locks across storage I/O.
- **No triggers** to sync aisle→inventory (would deadlock with inventory→aisle reconcile patterns).

---

## Idempotency model

- **DB unique indexes** are the final authority for duplicate prevention under concurrency.
- Application catches unique violations and maps to domain duplicate / conflict outcomes.
- Package re-confirm is idempotent: no new productives when already `CONFIRMED`.

Language to use: “idempotency enforced by UNIQUE X”; not “exactly-once everywhere.”

---

## Performance decisions

- Prefer set-based INSERT/UPDATE and chunked `executemany` / IN lists via `sql_batch.py`.
- Distinguish: Python cursor call ≠ ODBC network RPC ≠ SQL execution ≠ wall-clock.
- `fast_executemany`: **opt-in only** where NULL/datetime/rollback/large-batch SQL tests exist (`local_csv_inventory_result_writer`); default paths keep it **false**. Not expanded in Phase 6.
- Do not claim unmeasured wire-level RPC reductions.

---

## Stored Procedure decision

```text
Application Stored Procedures = 0
```

`sp_getapplock` (SQL Server native) is not an application SP.

**Future policy:** Do not add application SP unless measured ROI exists (lock contention, driver/network bottleneck, or atomicity backend TX cannot solve). Reopen Phase 4 only with new evidence.

---

## Trigger decision

```text
Application Triggers = 0 (live catalog verified)
```

**Future policy:** Do not add Trigger unless all Phase 5 A–I criteria are satisfied. Especially avoid triggers for `inventory.status`, `updated_at`, duplicate prevention, soft delete, or jobs without a fresh review.

---

## Migration state

| Item | Value |
| ---- | ----- |
| HEAD | `0095_aisle_scoped_counted_product_labels.sql` |
| Phase 6 new migrations | **0** |
| Critical integrity migrations present | 0044, 0056, 0074, 0084, 0094, 0095 |
| 0094 legacy secondary uniques | Removed (confirmed absent live) |
| 0095 `UQ_icpl_inventory_label` | Removed; `UQ_icpl_aisle_label` present |
| Test stub CAS hygiene | Position/finalization stubs inherit `ExplicitInventoryCompareAndSet` |

---

## Critical constraints / indexes

| Name | Role |
| ---- | ---- |
| `UQ_source_assets_aisle_upload_batch_client` | Upload idempotency |
| `UQ_eiar_idempotency_key` | External request idempotency |
| `UQ_source_assets_ordered_session_*` | Ordered capture |
| `UQ_manual_position_override_active` / `_idempotency` | Manual overrides |
| `UX_local_csv_productive_label` / import-row UQs | Local CSV |
| `UQ_icpl_aisle_label` | Counted labels (aisle-scoped) |

---

## completed_at follow-up (Phase 5 → Phase 6 closure)

**Decision: B — NO_ACTION (no CHECK).**

Evidence (integration DB, 2026-08-11):

```text
status = 'completed' AND completed_at IS NULL     → 0 rows
status <> 'completed' AND completed_at IS NOT NULL → 0 rows
```

Rationale:

1. `inventory.status` is a **derived projection**; `completed_at` is **projection metadata** repaired by `InventoryStatusReconciler` (`_completed_at_needs_fix` / CAS), not an independent SoT.
2. A CHECK would convert **repairable metadata drift** into hard write failures for any incomplete writer — worse operationally than reconciler repair.
3. Domain helpers `Inventory.mark_processing` / `mark_failed` now clear `completed_at` (aligned with reconciler) but are not the production status authority (CAS is).
4. No Trigger for this pairing (Phase 5 + Phase 6).

Follow-up status: **CLOSED** (not deferred).

---

## Recovery model

| Failure point | DB | Storage | Classification |
| ------------- | -- | ------- | -------------- |
| Package PLAN / REJECT | unchanged (rollback) | none | rolled back |
| STAGE storage | unchanged | partial assets possible | requires cleanup / retry; unique protects re-stage |
| Package APPLY mid-write | rolled back to PREVIEWED | staged assets may remain | retryable; detectable |
| Post-commit materialization | CONFIRMED stays | ok | retryable via idempotent re-confirm |
| Inventory reconcile CAS miss | no wrong overwrite | n/a | retryable / `RETRY_EXHAUSTED` |
| Inventory status drift | projection wrong until repair | n/a | detectable drift (`detect` / backfill) |

Callers of `reconcile() -> bool`: **True** only means `REPAIRED`. **False** is not “guaranteed consistent” (may be `CONSISTENT`, `NOT_FOUND`, or `RETRY_EXHAUSTED`). Critical callers today are best-effort; prefer `repair()` + outcome enum when correctness must be asserted.

---

## Test evidence

See `audit/db-integrity-final-validation.md` for commands and pass/fail counts.

Minimum suites: `db_integrity`, `inventory_status`, `local_inventory_package`, `local_csv_batch`, counted-label concurrency, domain derive, ports contract, package/CSV unit.

---

## Known residual risks

| Risk | Notes |
| ---- | ----- |
| One-shot backfill full scan | CLI maintenance cost on large fleets; intentional |
| Staged unused SourceAsset cleanup | After failed STAGE/APPLY, orphans may need ops cleanup |
| Eventual inventory status drift | Until reconcile/backfill; aisles remain SoT |
| Wire-level RPC not measured | Batching reduces cursor calls; do not claim network RPC deltas without traces |
| `reconcile() -> bool` ambiguity | Documented; callers best-effort |

---

## Operational guidance

1. Apply migrations to HEAD; pending must be 0 before release validation.
2. Prefer `detect` / backfill CLI for inventory projection drift; do not invent triggers.
3. On package confirm failure after STAGE: retry confirm; rely on UNIQUE + idempotent APPLY.
4. Treat unique violations as expected concurrency signals.
5. Keep `fast_executemany` scoped; do not enable globally.

---

## DB / application ownership matrix

| Concern | Owner |
| ------- | ----- |
| Authorization | Backend |
| Workflow | Backend |
| OCR/CV/LLM | Backend |
| Storage | Backend |
| Constraints | SQL Server |
| Unique / idempotency authority | SQL Server |
| Transaction orchestration | Backend repositories / use cases |
| CAS | SQL Server primitive via repository |
| Derived inventory status | Backend derive + DB persisted projection |
| Trigger logic | None |
| App Stored Procedures | None |

---

## Security review (Phases 0–6)

```text
NO_NEW_SECURITY_SURFACE
```

No new dynamic SQL surfaces, secrets in logs, weakened auth, or extra DB permissions introduced for this initiative. Parameterized SQL and existing auth boundaries preserved.

---

## Future-change decision ladder

When changing persistence behavior:

1. Can a CHECK / FK / UNIQUE solve it?
2. Can transaction boundaries solve it?
3. Can CAS solve it?
4. Can batching / set-based SQL solve it?
5. Is a view / function actually useful?
6. Is there measured ROI for an application SP?
7. Is a Trigger truly unavoidable (Phase 5 A–I)?

Do **not** reopen Phase 1–3 package TX, batching, D1 uniqueness, or reconciler design without a demonstrated bug.

Do **not** introduce framework layers (`DatabaseIntegrityManager`, `TriggerManager`, etc.) without a real consumer need.
