# Phase 7 — Rollback plan

## Compatibility matrix (N / N-1)

| Component | Forward | Rollback risk |
| --------- | ------- | ------------- |
| API image | N workers with N-1 API: avoid | Prefer API+worker same SHA |
| Worker image | N-1 worker with N schema: OK if additive migrations only | 0073 additive — safe |
| Migration 0073 | Rollback = DROP unique index | Re-creates duplicates risk if writes interleaved |
| Alert rules | Deploy previous `dinamic-phase5-alerts.yml` | Keep git tag of prior rules |
| Feature flags | Revert env | No fencing kill-switch |

## Steps

1. **Image**: redeploy previous digest-tagged images (`dinamic-api:<prev_sha>`, `dinamic-worker:<prev_sha>`).
2. **Config**: restore previous `.env` / secrets references (not values in git).
3. **Migration 0073** (only if required):
   ```sql
   DROP INDEX IF EXISTS UX_inventory_jobs_retry_of_job_id ON dbo.inventory_jobs;
   ```
   Then re-run preflight before reapply.
4. **Alerts**: `git checkout <prev_tag> -- deploy/prometheus/dinamic-phase5-alerts.yml` and reload Prometheus.
5. **Verify**: `/health`, `/ready`, one dry-run `recover_job`, metrics scrape.

## Active jobs during rollback

- Prefer drain: stop scheduler recovery, finish in-flight leases, then swap images.
- Do not run destructive DB cleanup during rollback.
