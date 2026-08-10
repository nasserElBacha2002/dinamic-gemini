# Phase 7 — Rollback plan (executed)

## Drill

Script: `scripts/release/run_rollback_drill.sh`

| Step | Result |
| ---- | ------ |
| Deploy N images | build/tag `dinamic-api/worker:${HEAD}` |
| Schema + seed job | OK |
| Deploy N-1 images | `9b78950c…` |
| API/worker import on N-1 | OK (with APP_ENV=development) |
| Rollback 0073 + reapply | OK |
| Duplicate `retry_of_job_id` rejected | OK |

Result: `ROLLBACK_DRILL_OK`
