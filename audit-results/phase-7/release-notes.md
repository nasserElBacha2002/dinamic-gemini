# Phase 7 — Release notes

## Summary

Phase 7 release hardening is **COMPLETED**:

- Fail-closed migration/smoke/E2E/security release scripts
- Docker base images pinned by digest
- `reconcile_aisle` visible stderr deprecation + tests
- Migration from-zero / 0073 rollback / backup-restore / N/N-1 drills executed on ephemeral DBs

## Ops notes

- Prefer physical SQL BACKUP on staging/prod engines; this developer Docker SQL returns Error 3041 for `BACKUP TO DISK`.
- Smoke requires `/ready=200` — do not treat 503 as success.
- Re-run `scripts/audit/run_full_audit.sh` after merge commit for `AUDIT_SHA=HEAD`.
