# Phase 5 — Recovery policy

## Manual recovery (primary)

```bash
python -m scripts.ops.recover_job --job-id <id> --dry-run --actor ops --reason 'stale-lease'
python -m scripts.ops.recover_job --job-id <id> --confirm --actor ops --reason 'stale-lease'
```

Invokes `RecoverStaleJobUseCase`:

1. Refuse active unexpired lease
2. Stale-fail CAS + aisle reconcile (no lease stealing)
3. Enforce `RECOVERY_MAX_ATTEMPTS` / attempt_count
4. Create child job with `retry_of_job_id` + same correlation_id / snapshot / assets
5. Launch exactly one worker via `AisleJobLaunchService`
6. Outcomes: `RECOVERED` | `DRY_RUN` | `ACTIVE_LEASE` | `NOT_STALE` | `MAX_ATTEMPTS` | `ALREADY_RECOVERED` | `LOST_CAS` | `RETRY_CREATE_FAILED` | `WORKER_LAUNCH_FAILED`

`job_recovery_completed` is emitted only for successful recovery / already-recovered paths — not for stale-fail alone.

## Automatic recovery (optional)

Settings (validated):

| Env | Constraint |
| --- | ---------- |
| `RECOVERY_ENABLED` | default `false`; must be explicit for scheduler |
| `RECOVERY_INTERVAL_SEC` | 1..3600 |
| `RECOVERY_BATCH_SIZE` | 1..200 |
| `RECOVERY_MAX_ATTEMPTS` | 1..50 |

When enabled, API startup starts `StaleJobRecoveryScheduler` using the same use case as the CLI. Cooperative shutdown on API stop. No lease stealing.

## Consistency audit

```bash
python -m scripts.ops.audit_job_state_consistency --dry-run --limit 200
```

Uses `JobRepository.list_jobs_for_ops_scan` (fails if unsupported). Empty DB → `jobs_scanned=0` success; unsupported backend → non-zero exit.

## Migration 0073 preflight (`retry_of_job_id` uniqueness)

Before applying `0073_inventory_jobs_retry_of_unique.sql`:

```bash
python -m scripts.ops.preflight_0073_retry_of_duplicates
```

See `backend/src/database/migrations/versions/0073_README.md` for duplicate resolution, rollback (`DROP INDEX`), and reapply steps.

## Aisle inspect

```bash
python -m scripts.ops.inspect_aisle --aisle-id <id> --dry-run --actor ops --reason 'check'
```

Read-only. Mutating reconcile remains admin APIs (`--confirm` refused).
