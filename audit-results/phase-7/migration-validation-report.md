# Phase 7 — Migration validation report

## 0073

Script: `scripts/release/validate_migration_0073.sh`

Flow: verify → preflight → rollback (DROP INDEX) → reapply → verify.

Result: `MIG_0073_VALIDATION_OK` · schema_version=`0073` · index_state=`present`.

## From zero / upgrade

Script: `scripts/release/validate_migrations_from_zero.sh`

- **A)** Schema-only clone of `dinamic-gemini` (0073) + migration history copy → validate → API `/ready=200` → rollback/reapply 0073  
- **B)** Idempotent apply on full clone  
- **C)** Concurrent insert uniqueness (IntegrityError expected)  
- **D)** Upgrade 0072 → 0073 (hide 0073 file, delete row, restore, apply)

Note: `0001_baseline.sql` is metadata-only; empty DB bootstrap uses schema-only clone of a 0073-compatible source (repo contract). `dinamic_inventory_test` at 0004 is incomplete for 0005+ (missing legacy `jobs`).

Result: `MIGRATIONS_FROM_ZERO_OK`.
