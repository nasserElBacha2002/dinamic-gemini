# Release notes — Phase 7 (release hardening)

**Version:** pending tag (recommend `vX.Y.Z-rc1` from commit that includes these docs)  
**Base precondition SHA:** `9b78950c33d4d3dbb905aa8deeb893b5832930b9`

## Scope

Final cleanup / release readiness: documentation, ops deprecations, release smoke/e2e helpers, metrics catalog correction, Docker ignore hardening. **No new product features.** No OCR/CODE_SCAN/prompt behavior changes.

## Functional changes

- None intended for operators beyond clearer error paths already shipped in Phase 5/6.

## Internal changes

- `scripts.ops.reconcile_aisle` deprecated (sunset 2026-12-31) in favor of `inspect_aisle`.
- Release scripts under `scripts/release/`.
- Metrics catalog: recovery alerts map to `stale_recovery_scheduler_*` (not PLANNED `job_recovery_total`).

## Migrations

- 0073 remains additive unique index on `retry_of_job_id` with preflight for duplicates.

## Environment

- No env vars removed. Continue documenting via `.env.example`.

## Breaking changes

- None this slice. After 2026-12-31, remove `reconcile_aisle` CLI alias.

## Deprecations

- CLI `reconcile_aisle` → `inspect_aisle`
- Prefer digest-pinned Docker bases in a follow-up

## Rollback

See `audit-results/phase-7/rollback-plan.md`.

## Known risks

- trivy/hadolint not present in this workstation — install for full security DoD.
- Live photo→LLM E2E remains a staging runbook item.
- Empty-DB migration apply should be confirmed in CI/staging before production.
