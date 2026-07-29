# Phase 7 — Backup / restore notes

## Before production cutover

1. Full SQL Server backup (full + log as per ops RPO).
2. Record `schema_migrations` / migration version table state.
3. Snapshot artifact storage references (GCS prefixes / local volume paths) — not secrets.
4. Export Prometheus alert rule file revision (git SHA).
5. Document secret **references** (names in secret manager), never values.

## Restore drill (staging)

1. Restore backup to isolated instance.
2. Point a staging API at restored DB (read-only first).
3. Run `/health`, `/ready`, `preflight_0073`, one `inspect_job`.
4. Measure time → propose RTO; backup frequency → propose RPO (**operational proposal only**).

## This phase

No production backup was executed from this agent session.
