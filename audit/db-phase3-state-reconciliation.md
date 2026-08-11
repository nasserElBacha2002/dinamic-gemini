# Fase 3 — State reconciliation, drift detection, consistency observability

**Resultado:** `COMPLETE`  
**Fecha:** 2026-08-11  
**Stored Procedures added:** 0  
**Triggers added:** 0  
**Reconciliation jobs added:** 0 (reuses one-shot CLI `backfill_inventory_status`; no new scheduler)  
**Drift detectors added:** 1 (`InventoryStatusReconciler.detect`)

## Executive summary

Inventory status was already a derived projection with a single derive function and reconciler. Phase 3 formalizes **detect vs repair**, reason codes, structured logs, compare-and-set persistence, detect-only CLI, and SQL/unit evidence that post-commit drift is recoverable and idempotent. No triggers; no new SPs.

## State classification

| Entity | Persisted state | Type | Source of truth | Reconciler |
| ------ | --------------- | ---- | --------------- | ---------- |
| Inventory | `status` | **B Fully derived** | Active aisle statuses | `InventoryStatusReconciler` |
| Aisle | `status` | A / C workflow | Jobs, uploads, review | Domain transitions (not inventory rollup) |
| InventoryJob | job status | C / D | Worker + CAS | `JobStaleReconciler` (out of scope) |
| LocalCsvImport | PREVIEWED/CONFIRMED | A / D event | Confirm TX | No inventory-style rollup |
| LocalInventoryPackage | PREVIEWED/CONFIRMED | A / D event | Confirm TX | Post-commit aisle mark → inventory reconcile |
| SourceAsset | metadata | A | Upload path | Orphan policy (Fase 2); not status rollup |

## Drift risks found

| Risk | Mitigation |
| ---- | ---------- |
| Post-commit aisle mark without inventory update | Re-confirm / `repair` / CLI backfill |
| Forgotten reconcile call sites | Central materializer + many hooks; CLI detect-only audit |
| Concurrent reconcile vs worker | `compare_and_set_status` + re-detect on mismatch |
| Wrong COMPLETED when aisles incomplete | Full maintenance scan includes completed inventories |

## Reconciliation rules

Single pure function: `derive_inventory_status_with_reason(aisles)` → `(status, reason)`.

Reasons: `NO_OPERATIONAL_AISLES`, `ANY_AISLE_FAILED`, `AISLE_QUEUED_OR_PROCESSING`, `AISLE_PROCESSED_OR_IN_REVIEW`, `ALL_AISLES_COMPLETED`, `AISLE_SETUP_ACTIVITY`, `FALLBACK_DRAFT`.

Inactive aisles excluded via `scope_from_aisles(...).operational_aisles`.

No CANCELLED/ARCHIVED inventory states exist — no destructive overwrite of such terminals.

## Changes implemented

- Derive returns reason codes; status-only wrapper kept for compatibility.
- `detect()` / `repair()` / `reconcile()` on `InventoryStatusReconciler`.
- `InventoryStatusDrift` contract.
- Zero writes when `stored == expected`; no false `updated_at` bumps.
- Structured logs: `action=detected|repaired|consistent|cas_miss`.
- SQL + memory `compare_and_set_status`.
- CLI `--detect-only` on `python -m src.backfill_inventory_status`.
- Unit + SQL integration tests (detect, repair, idempotency, concurrency, post-commit recovery).

## Detect vs repair architecture

```text
detect(inventory_id) → InventoryStatusDrift | None   # read-only
repair(inventory_id) → drift if written               # idempotent
reconcile(inventory_id) → bool                        # repair wrapper (call-site compatible)
```

Admin: `BackfillInventoryStatusesUseCase(detect_only=True|False)`.

## Concurrency model

Short read of inventory + aisles → derive → CAS `UPDATE … WHERE status = expected_current`.  
CAS miss → no blind overwrite; safe to retry later.

## Post-commit recovery

Package/CSV confirm keeps primary TX committed; aisle finalize + inventory reconcile run post-commit (materializer). If reconcile fails, primary data remains; `detect` shows drift; `repair` / re-confirm / CLI fix it without duplicating productives.

## Observability

Structured logs (no new metrics stack). Detect-only CLI prints drifts. No new public API / UI (documented as future if admin panel exists).

## Tests

- Domain derive combinations + reasons
- Unit detect/repair/idempotency/post-commit recovery/CAS
- SQL detect+repair idempotent + concurrent repair
- Regression: local package/CSV suites

## Residual risks

- One-shot CLI still uses `list_all` (acceptable for maintenance, not a frequent worker).
- Position/product/asset consistency remains out of scope (status-only phase).
- Job stale reconciler unchanged.

## Final

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
PHASE_3: COMPLETE
Stored Procedures added: 0
Triggers added: 0
Reconciliation jobs added: 0
Drift detectors added: 1
```

| Estado derivado | Antes | Después | Recovery | Observabilidad |
| --------------- | ----- | ------- | -------- | -------------- |
| Inventory.status | derive + reconcile bool | detect/repair + reasons + CAS | CLI / re-confirm / repair | structured logs + detect-only |
