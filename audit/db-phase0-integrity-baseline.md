# Fase 0 — Baseline de integridad DB (post-corrections)

**Resultado:** `COMPLETE`  
**Fecha:** 2026-08-11  
**SPs added:** 0  
**Triggers added:** 0  
**Fuente de verdad:** migrations (`0095` HEAD on validation DB)

## Evidence

- Catalog suite: `tests/integration/db_integrity/test_critical_unique_indexes_catalog.py`
  - SQL unavailable → module skip via `sql_server_client_or_skip`
  - SQL available + missing critical index → **FAIL**
  - Migrations applied via `ensure_sql_migrations_applied` before assertions
  - Filtered index predicates asserted; 0094 legacy unique removed; 0095 aisle_id NOT NULL + FK + `UQ_icpl_aisle_label`
  - Behavior: upload idempotency duplicate rejected; NULL filter columns allowed
- D1 concurrency: `test_sql_inventory_counted_product_label_concurrency.py` **passed** on migrated test DB
- Validation DB `dinamic_inventory_test` current_version **0095**, pending **[]**

## Drift

| Expected | Actual | Action |
| -------- | ------ | ------ |
| 0094/0095 on validation DB | Present after repair+migrate | Done |
| schema.sql mirror | Still incomplete vs migrations | Documented; migrations remain authority |
