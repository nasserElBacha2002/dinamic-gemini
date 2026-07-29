# Phase 7 — Cleanup matrix

Generated against HEAD `9b78950c` after Quality Gate PASS. Classifications require
wiring/tests/docs evidence — not grep-only.

| Candidate | Area | Evidence | Dynamic? | Class | Notes |
| --------- | ---- | -------- | -------- | ----- | ----- |
| `LEGACY_LLM` execution for **new** jobs | backend | `reject_legacy_effective_mode_for_new_job` | no | KEEP | New starts rejected; historical jobs readable |
| Historical LEGACY_LLM job rows | backend | resolver docstring | no | KEEP | Read path required |
| `scripts.ops.reconcile_aisle` | scripts | thin alias → inspect_aisle | no | DEPRECATE | Sunset **2026-12-31**; warning added |
| `scripts.ops.inspect_aisle` | scripts | recovery-policy, README | no | KEEP | Canonical inspect |
| `scripts.ops.recover_job` | scripts | RecoverStaleJobUseCase | no | KEEP | |
| `scripts.ops.cleanup_junk_clients` | scripts | README local-only | no | KEEP | Never production |
| `scripts.ops.preflight_0073_*` | scripts | migration 0073 | no | KEEP | |
| Memory repositories | infra | tests + AppContainer memory mode | no | KEEP | Hosted must use SQL |
| PLANNED metrics in catalog | obs | metrics-catalog.md | n/a | KEEP | Not in prod alerts |
| `job_recovery_total` in alerts | obs | was mis-documented | n/a | REMOVE (docs) | Alert uses `stale_recovery_scheduler_*` |
| `EXTERNAL_FALLBACK_PER_IMAGE_*` | config | start_aisle_processing | no | KEEP | Active product path |
| `PER_ASSET` fallback mode | config | deprecation note in code | no | DEPRECATE | Temporary rollback; keep until GLOBAL_BATCH validated |
| OCR / CODE_SCAN paths | pipeline | Dockerfile installs binaries | no | KEEP | Out of Phase 7 functional change |
| Frontend v3 API client | FE | sole client | no | KEEP | No legacy v1/v2 client found |
| Mobile Expo app | mobile | active | no | KEEP | |
| Docker `python:3.11-slim` floating tag | docker | Dockerfile FROM | n/a | DEPRECATE | Prefer digest pin in next release |
| `latest` image tags | release | not used in compose | n/a | KEEP | Compose builds local context |
| Admin finalization `reconcile_aisle` op | API | RecoveryOperation | no | KEEP | Distinct from CLI alias |
| Empty / flaky FE pagination | FE | fixed in Phase 5/6 | n/a | KEEP | |
| Migration historical versions 0001–0072 | DB | applied chain | n/a | KEEP | Never squash |
| Migration 0073 unique retry_of | DB | additive + preflight | n/a | KEEP | |
| Physical drop of unused columns | DB | unknown readers | n/a | MIGRATE_FIRST | Post-release |
| trivy / hadolint | security | not installed locally | n/a | UNKNOWN | Required for full DoD; document NOT_AVAILABLE |

## Safe first slice (this phase)

1. Correct metrics catalog alert mapping for recovery.
2. Formalize `reconcile_aisle` CLI deprecation + sunset.
3. Add `scripts/release/*` smoke/e2e/migration helpers.
4. Expand ops README + phase-7 reports.
5. Harden `.dockerignore` / `.gitignore` for review dumps.
6. Validate Docker builds by digest-tagged SHA.
7. Re-run QG after commit (artifacts gitignored except audit-results docs).
