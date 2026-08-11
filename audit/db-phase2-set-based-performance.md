# Fase 2 — Set-based persistence / round-trip reduction (post code-review corrections)

**Resultado:** `COMPLETE`  
**Fecha:** 2026-08-11  
**Stored Procedures added:** 0  
**Triggers added:** 0  
**New indexes:** 0  
**New migrations:** 0  

## Executive summary

Optimizaciones HIGH/MEDIUM sobre Local CSV / Package confirm, con métricas **desambiguadas**:

| Metric | What it means | Status |
| ------ | ------------- | ------ |
| Python cursor calls | `execute` / `executemany` invocations from app code | **Measured** (CountingCursor + benches) |
| Driver executions | How ODBC expands each call | Not instrumented separately |
| SQL statements | T-SQL text sent | Same statement reused by `executemany` |
| Network RPCs / round trips | Wire-level batches | **Not claimed** (no RPC counter in stack) |
| Wall-clock duration | `perf_counter` around insert TX | **Measured** on SQL Server |

## Candidates analyzed

| ID | Flow | Recommendation | Outcome |
| -- | ---- | -------------- | ------- |
| C1 | productive `apply_import` | HIGH | `executemany` + **scoped `fast_executemany=True`** after benches |
| C2 | `find_confirmed_secondary_keys` | HIGH | candidate VALUES joins + parity vs full-scan |
| C3 | `_persist` import rows | MEDIUM | `executemany` with `fast_executemany=False` |
| C4 | post-commit list | MEDIUM | `list_for_import` reuse |
| C5 | D1 `try_claim` | NO_ACTION | concurrency authority |
| C6 | aisle get_by_id | NO_ACTION | low volume |

## Metric honesty (C1)

### Python cursor calls (demonstrable)

```text
100 rows
BEFORE: ~100 SELECT + ~100 INSERT = ~200 cursor.execute calls
AFTER:  1 SELECT IN (...) + ceil(100/80) executemany calls (= 2)
→ ~198 explicit Python cursor.execute calls eliminated
(not “~197 network round trips”)
```

### Wall-clock (SQL Server, dinamic_inventory_test, 2026-08-11)

| n | row-by-row ms | executemany (fast=False) ms | executemany (fast=True) ms |
| -: | ------------: | --------------------------: | -------------------------: |
| 10 | 6.8 | 6.4 | 7.7 |
| 100 | 34.5 | 29.7 | 10.0 |
| 1000 | 306.8 | 292.3 | 82.7 |

Plain `executemany` alone: small wall-clock gain.  
`fast_executemany=True` on productive INSERT: clear wall-clock gain at 100/1000; NULL/datetime + TX rollback covered by integration test. Enabled **only** on that INSERT path (restored on shared cursor).

**Network RPCs:** not measured → not asserted.

## Chunk sizes

| Constant | Purpose | Rationale |
| -------- | ------- | --------- |
| `SQL_IN_CHUNK_SIZE` / `SQL_VALUES_PAIR_CHUNK_SIZE` | Multi-param **single** statement | SQL Server ~2100 param budget |
| `EXECUTEMANY_PRODUCTIVE_PARAM_SET_CHUNK` (=80) | Driver parameter-*set* chunking | Memory/driver behaviour — **not** `25×80 < 2100` |
| `EXECUTEMANY_IMPORT_ROW_PARAM_SET_CHUNK` (=70) | Same for row UPDATE | Same distinction |

## C2 secondary keys

Candidate-scoped VALUES joins retained.  
Parity test: `find_confirmed_secondary_keys` == `find_confirmed_secondary_keys_full_scan` for `label:` / `photo:` / `pos:`.  
Unknown suffix → `ValueError` (forces query update if domain adds shapes).

## PLAN → STAGE → APPLY race

Integration test pauses after PLAN, lets a concurrent CSV confirm claim the secondary key, then resumes STAGE/APPLY.

Expected (observed):

- losing package row → `DUPLICATE` (SKIP)
- winner → single productive row
- 0 productive duplicates
- unique constraints intact

### Orphan staged assets policy

```text
staged SourceAsset  ≠  confirmed productive evidence
```

Between PLAN unlock and APPLY revalidation, staging may create a SourceAsset for a row that later becomes DUPLICATE.

**Policy:** recoverable orphan scoped by `upload_batch_id=package.id`, unreferenced by `local_csv_productive_results.source_asset_id`.  
**Not** deleted inline (unsafe under concurrency). Retry uses upload idempotency keys. Hard cleanup deferred to business-data cleanup / future reaper.

Documented on `_stage_source_assets_for_rows`.

## sqlserver_business_data_cleanup.py

Change kept: DELETE order includes local CSV/package tables + `inventory_counted_product_labels` **before** `source_assets` so pytest/business cleanup does not trip FKs.  
Used only by `clean_local_business_data` / test cleanup — not application runtime.

## Git hygiene

Large `audit/*-diff.txt` / `*-diffstat.txt` / `*-status.txt` dumps are gitignored; architecture `*.md` reports remain versionable.

## Transaction impact

Fase 1 atomicity preserved: productive + CSV CONFIRMED + package CONFIRMED on one connection / one commit; writer reuses caller cursor; no storage under SQL locks.

## Tests

- Unit CountingCursor (Python call shape)
- SQL batch happy/rollback/idempotent/nullables
- SQL executemany benchmark 10/100/1000 + fast rollback
- Secondary-key parity + unknown prefix
- PLAN→APPLY race (two connections/threads)
- Package confirm + db_integrity + D1 concurrency regressions

## Final

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
Stored Procedures added: 0
Triggers added: 0
New migrations: 0
New indexes: 0
```

| Cambio | Cursor calls | Network RPCs | Wall-clock | Riesgo |
| ------ | ------------ | ------------ | ---------- | ------ |
| Productive INSERT batch + fast | ↓ measured | not measured | ↓ at 100/1000 | bajo (scoped) |
| Secondary keys candidate | 1–2 scoped queries vs full scan | n/a | scales with candidates | bajo |
| Import row executemany | ↓ Python calls | not measured | modest | bajo |
| list_for_import | 1 vs 2 inventory lists | n/a | less IO | bajo |
