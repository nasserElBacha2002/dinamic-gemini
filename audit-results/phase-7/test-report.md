# Phase 7 — Test report

## Precondition (HEAD 9b78950c, clean tree)

| Suite | Result |
| ----- | ------ |
| backend/tests | 4028 passed, 6 skipped |
| backend/tests/integration | 18 passed |
| frontend vitest | 1223 passed |
| mobile jest | 139 + 10 integration |
| promtool | SUCCESS |
| Quality Gate | PASS (`20260729T160325Z`) |

## Phase 7 added validation (this session)

| Command | Result |
| ------- | ------ |
| `bash scripts/release/run_smoke_tests.sh` | **SMOKE_OK** (25 pytest + health/ready) |
| `bash scripts/release/run_e2e_release_validation.sh` | **E2E_RELEASE_VALIDATION_OK** (18+21+1) |
| Docker `dinamic-api:9b78950c` | build OK |
| Docker `dinamic-worker:9b78950c` | build OK |
| promtool test rules | SUCCESS |
| `validate_migration_0073.sh` preflight | no duplicates (exit 0) |
| db_migrate status (local pointed DB) | reports pending 0005–0073 — **staging empty-DB apply still required** |
| trivy / hadolint | NOT_AVAILABLE |

Re-run full audit after committing Phase 7 so `AUDIT_SHA` matches the release commit.
