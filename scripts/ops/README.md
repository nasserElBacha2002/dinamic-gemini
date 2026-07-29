# Operational CLIs (Phase 5–7)

Run from repository root with `PYTHONPATH=backend` (or `backend/.venv/bin/python` and
module paths as shown). Prefer dry-run before confirm.

## Supported

| Command | Purpose |
| ------- | ------- |
| `python -m scripts.ops.audit_job_state_consistency --dry-run` | Scan job/aisle consistency |
| `python -m scripts.ops.inspect_job --job-id <id>` | Inspect one job |
| `python -m scripts.ops.inspect_aisle --aisle-id <id> --dry-run --actor <ops> --reason '<why>'` | Read-only aisle inspect |
| `python -m scripts.ops.recover_job --job-id <id> --dry-run --actor <ops> --reason '<why>'` | Stale job recovery (RecoverStaleJobUseCase) |
| `python -m scripts.ops.preflight_0073_retry_of_duplicates` | List duplicate `retry_of_job_id` before UX index |

## Deprecated aliases

| Alias | Prefer | Sunset |
| ----- | ------ | ------ |
| `python -m scripts.ops.reconcile_aisle` | `inspect_aisle` | 2026-12-31 |

## Local-only (never production)

| Command | Purpose |
| ------- | ------- |
| `backend/.venv/bin/python scripts/ops/cleanup_junk_clients.py --confirm` | Dev DB junk client cleanup |

See `audit-results/phase-5/recovery-policy.md` and `audit-results/phase-7/`.
