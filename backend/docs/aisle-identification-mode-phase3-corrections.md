# Aisle identification — Phase 3 (CODE_SCAN) corrections note

## Feature flag (required for production rollout)

```env
CODE_SCAN_PROCESSING_ENABLED=false   # default OFF
```

| Mode | Flag | Snapshotted `execution_strategy` |
|------|------|----------------------------------|
| CODE_SCAN | true | `CODE_SCAN` |
| CODE_SCAN | false + pipeline on | `LEGACY_LLM_TEMPORARY` (`reason=CODE_SCAN_PROCESSING_ENABLED_FALSE`) |
| CODE_SCAN | false + pipeline off | `LEGACY_LLM` |

The worker trusts **only** the immutable job `execution_strategy` (and `engine_params_json.identification_execution`). Retries copy the original snapshot and do **not** re-read env flags.

## Rollback

Set `CODE_SCAN_PROCESSING_ENABLED=false` — no redeploy of strategy code required for new jobs.

## Concurrency

Keep `MAX_IMAGE_PROCESSING_CONCURRENCY=1` until SQL Server concurrency tests pass.

See also `aisle-identification-mode-phase3.md` (architecture) and `aisle-identification-mode-phase4.md`.
