# Physical Product Labels D1 — Implementation Corrections Report

**Date:** 2026-08-10  
**Branch:** DIN-288  
**Final status:** `CORRECTIONS_WITH_WARNINGS`

## Summary

Corrections close the integrity gaps from code review: D1 is countable only when format + checksum + **issued registry** + **client match** + **payload match** + not yet claimed. ALL_LABELS_DUPLICATE no longer creates empty Positions. Claim repo is fail-closed. Typed `ProcessedProductLabel`, SQL unique-violation encapsulation, migrations 0089/0090, local CSV `label_id`, export batching, mint auth, shared checksum CI, and restored `audit-results/**`.

## Root causes → fixes

| Issue | Root cause | Fix |
|-------|------------|-----|
| Count without issued ID | Parser+checksum treated as sufficient | `IssuedProductLabelResolver` + strategy gate |
| Trust scan SKU/qty | Scan payload used as SoT | Registry fields are SoT; mismatch → `PAYLOAD_MISMATCH` |
| Empty Position on all-dup | Persist always created Position | Early return `ALL_LABELS_DUPLICATE` |
| Best-effort claim | `object` / optional repo | Required typed repo; raise if D1 without claim |
| Dict product_results | Untyped pipeline | `ProcessedProductLabel` domain DTO |
| SQL message sniffing in UC | Driver text in application | `is_sql_unique_violation` in infra + typed errors |
| Weak constraints | 0088 minimal | 0089 quantity/len checks; FKs documented omitted |
| client_id from client | Job params trusted | Inventory `client_id` preferred in asset processor |
| Mint `_principal` unused | Auth incomplete | `require_client_scope` |
| Export N+1 | Per-position list | `list_by_position_ids` once |
| Local CSV no label_id | Schema v1 only | Parser 1/1.1 + 0090 + materializer claim |
| Silent candidate truncate | Magic `12` | `CodeScanConfig.max_candidates_per_asset` + metric/log |
| Accidental audit deletes | Phase-1 commit | Restored via `git checkout` |

## Architectural decisions

1. **Parse vs resolve:** deterministic I/O-free parser; registry I/O only in `IssuedProductLabelResolver`.
2. **Functional outcomes:** status enums, not exceptions, for expected rejects.
3. **Mint non-idempotent:** documented — each POST creates new physical IDs (no Idempotency-Key).
4. **No FK `product_records.label_id → issued`:** legacy NULL + transactional claim order (documented in 0089).
5. **No FK on claim `first_*`:** claim inserts before product row with preallocated UUID; same TX for atomicity.

## Migrations

| Migration | Purpose |
|-----------|---------|
| 0088 | Baseline tables (unchanged history) |
| 0089 | Quantity range, `LEN(label_id)=10`, checksum len |
| 0090 | Nullable `label_id` on local CSV import/productive rows |

**SQL up/down/up on real server:** not executed in this environment (no live SQL Server). Scripts present under `backend/src/database/migrations/versions/`.

## SQL concurrency

Tests in `backend/tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py`:

- two workers → one True / one False  
- claim + rollback → label available again  

**Result this run:** `2 skipped` (SQL Server unavailable). Must run in CI/env with ODBC + migrated DB before production.

## Validation results

### Backend (targeted)

- `domain/product_labels` + image_processing + product_labels UC + local CSV materializer: **276 passed, 2 skipped**
- Memory claim + issue auth: **passed**
- Full `backend/tests/infrastructure`: **pre-existing** collection error (`google.api_core` missing) — unrelated

### Frontend

- typecheck: **pass**
- lint: **0 errors** (pre-existing refresh warnings)
- vitest productLabelPayload + JobImageResultCard: **7 passed**
- build: **pass**

### Mobile

- typecheck: **pass**
- productLabelChecksumVectors + multi consolidator: **5 passed**
- localCsv suites: **pass** (schema 1.1 + `label_id` column)

### CI

- New job `product-label-contract` in `develop-quality-gate.yml` (backend + frontend + mobile golden vectors)
- `mobile-validate.yml` watches `contracts/product-labels/**`

## Restored files

All `audit-results/phase-0` … `phase-7` docs restored (staged `A`).

## Remaining risks / follow-ups

1. **SQL concurrency + migration up/down/up** must be green on real SQL Server.
2. Mobile still stores **one confirmed product per photo**; CSV emits `label_id` when present but multi-row D1 ZIP from device needs draft/confirm multi-product persistence.
3. Aisle **positions table** still primary-SKU oriented; `detected_products` is documented and shown on image cards when present — full positions multi-SKU UX is follow-up.
4. Bridge logs and continues if issued resolver wiring fails → D1 fails closed at strategy (`PRODUCT_LABEL_RESOLVER_UNAVAILABLE`).

## Deliverables

- `implementation-corrections-status.txt`
- `implementation-corrections-diffstat.txt`
- `implementation-corrections-diff.txt`
- `review/latest-*.txt` + `review/product-labels-d1-corrections-*.txt`
