# Stage 1 — Limitations and residual risks

| ID | Limitation | Severity | Notes |
|----|------------|----------|-------|
| L1 | Full pytest not green on first pass (3 flakes) | MEDIUM | Re-ran green; do not treat suite as perfectly stable |
| L2 | `test_sql_stale_reclaim_one_winner` can deadlock | MEDIUM | Pre-existing SQL contention; outside claim_cycle idle fix |
| L3 | No remote probe when `EMBEDDED_WORKER_ENABLED=false` | LOW | Documented; dedicated worker health is ops concern |
| L4 | FastAPI `on_event` still deprecated | LOW | Pre-existing |
| L5 | DEV OpenCloud spam not re-observed live | LOW | Covered by unit contract |
| L6 | Legacy bridge not deleted | INFO | Still optional for historical drain; verify producers before removal |
| L7 | Cleanup fixture FK conflict on some SQL integration runs | LOW | `DELETE clients` vs `FK_inventories_client` when auto-cleanup on |

## Residual operational risks

- If someone re-enables the Stage-8 bridge without a `jobs` table, polls may log legacy exceptions; v3 idle remains healthy (by design) but logs will noise.
- Singleton `EmbeddedWorkerRuntime` is process-global; tests must call `reset_embedded_worker_runtime_for_tests()`.
