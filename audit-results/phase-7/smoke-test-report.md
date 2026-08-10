# Phase 7 — Smoke test report

Script: `scripts/release/run_smoke_tests.sh`

| Check | Result |
| ----- | ------ |
| Ephemeral DB (schema clone 0073) | OK |
| API uvicorn startup | OK |
| GET `/health` | **200** |
| GET `/ready` | **200** (503 fails the script) |
| Body: schema_compatible / repository_backend_healthy | OK |
| GET `/metrics` | 200 |
| Worker bounded startup | OK (`worker_startup_ok`) |
| Clean shutdown | OK |

Result: `SMOKE_OK`
