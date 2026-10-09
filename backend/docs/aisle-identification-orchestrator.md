# Aisle identification — Phase 2 (image processing orchestrator)

## Goal

Introduce per-asset processing state, exclusive batch lease, and attempt history around
`process_aisle` jobs **without changing** the productive legacy hybrid LLM behavior.

## Audit summary (current pipeline)

- Assets are processed as **AISLE_BATCH**: all aisle photos → one hybrid LLM analysis.
- Persist is delete-and-replace by `job_id` via `PersistAisleResultUseCase`.
- Fase 1 snapshot fields are immutable on the job; worker does not re-resolve config.
- Insertion point: `V3JobExecutor._v3_run_job_body` after prep, gated by flags.

## Architecture (Phase 2 corrections)

```text
V3JobExecutor
  ├─ IMAGE_PROCESSING_ORCHESTRATOR_ENABLED=false → exact legacy path
  └─ =true → AisleProcessingOrchestrator
        → ensure JobAssetProcessingState rows
        → recover abandoned lease / states / STARTED attempts
        → acquire JobProcessingLease (job_id, strategy, execution_scope)
        → create BatchProcessingAttempt STARTED (+ logical asset attempts)
        → LegacyLlmProcessingStrategy (one AISLE_BATCH runner)
        → synthesize via AssetResultCoverageResolver
        → finalize attempts + lease
        → merge asset_progress into job.result_json (locked merge)
```

### Locking

| Layer | Key | Purpose |
|-------|-----|---------|
| Batch lease | `(job_id, strategy, execution_scope)` | Exactly one physical provider call |
| Asset state | `job_id + asset_id` + `worker_token` + `version` | Ownership + optimistic locking (prepared for Phase 3) |

Asset locks alone are **not** sufficient while physical scope is `AISLE_BATCH`.

### Feature flag combinations

| Orchestrator | Attempts | Behavior |
|--------------|----------|----------|
| off | * | Exact legacy; no states/attempts |
| on | off | States + progress + lease; `attempt_count` still increments; no detailed attempt rows |
| on | on | Full batch + logical attempt history |

### `FAILED_TECHNICAL` policy (Phase 2)

Terminal **within the same job**. Abandoned `PROCESSING` recovers to `PENDING` (not
`FAILED_TECHNICAL`). A full retry creates a new job.

### `MAX_IMAGE_PROCESSING_CONCURRENCY`

Reserved for Phase 3 `SINGLE_ASSET`. Validated `>= 1`. Does **not** parallelize the
legacy aisle batch in Phase 2.

## Feature flags (defaults safe)

| Env | Default | Role |
|-----|---------|------|
| `IMAGE_PROCESSING_ORCHESTRATOR_ENABLED` | false | Enable orchestrator bookkeeping |
| `PROCESSING_ATTEMPTS_ENABLED` | false | Persist ProcessingAttempt / batch attempt detail |
| `MAX_IMAGE_PROCESSING_CONCURRENCY` | 1 | Reserved for Phase 3 (not applied to AISLE_BATCH) |
| `IMAGE_PROCESSING_BATCH_LEASE_SECONDS` | 900 | Exclusive batch lease TTL |
| `IMAGE_PROCESSING_ABANDONED_TTL_SECONDS` | 900 | Abandoned PROCESSING / STARTED recovery |
| `AISLE_IDENTIFICATION_PIPELINE_ENABLED` | false | Fase 1 snapshot labeling |

## Tables

- `0051` — `job_asset_processing_states`, `processing_attempts`
- `0052` — `job_processing_leases`, `batch_processing_attempts`, additive columns
  (`worker_token`, `lease_expires_at`, `parent_batch_attempt_id`, `batch_execution_id`, …)

## SQL backend policy

When `APP_REPOSITORY_BACKEND` resolves to SQL, Phase 2 repos **must** be SQL.
Missing migration / table → `ImageProcessingRepositoryUnavailableError` (fail fast).
No silent fallback to in-memory repos.

## API

Additive `JobSummary.asset_progress` from `result_json.asset_progress` (also derivable
from the states table via `aggregate_progress`).

## Out of scope (Phase 3+)

QR/barcode/OCR, per-image LLM, `CodeScan`/`InternalOcr` strategies, multi-provider
fallback, frontend reprocess, prompt/quantity/dedup rule changes.
