# Aisle identification — Phase 2 (image processing orchestrator)

## Goal

Introduce per-asset processing state and attempt history around `process_aisle` jobs
**without changing** the productive legacy hybrid LLM behavior.

## Audit summary (current pipeline)

- Assets are processed as **AISLE_BATCH**: all aisle photos → one hybrid LLM analysis.
- Persist is delete-and-replace by `job_id` via `PersistAisleResultUseCase`.
- Fase 1 snapshot fields are immutable on the job; worker does not re-resolve config.
- Insertion point: `V3JobExecutor._v3_run_job_body` after prep, gated by flags.

## Architecture

```text
V3JobExecutor
  ├─ IMAGE_PROCESSING_ORCHESTRATOR_ENABLED=false → exact legacy path
  └─ =true → AisleProcessingOrchestrator
        → ensure JobAssetProcessingState rows
        → LegacyLlmProcessingStrategy (AISLE_BATCH runner)
        → synthesize logical per-asset states + ProcessingAttempts
        → attach asset_progress to job.result_json
```

### Limitation (documented)

Physical LLM execution remains **one aisle batch**. Per-asset rows are
`execution_scope=AISLE_BATCH` with `logical_asset_attempt=true`. Phase 3 can
switch to `SINGLE_ASSET` without rewriting persistence contracts.

## Feature flags (defaults safe)

| Env | Default | Role |
|-----|---------|------|
| `IMAGE_PROCESSING_ORCHESTRATOR_ENABLED` | false | Enable orchestrator bookkeeping |
| `PROCESSING_ATTEMPTS_ENABLED` | false | Persist ProcessingAttempt rows |
| `MAX_IMAGE_PROCESSING_CONCURRENCY` | 1 | Reserved for Phase 3+ |
| `AISLE_IDENTIFICATION_PIPELINE_ENABLED` | false | Fase 1 snapshot labeling |

## Tables (migration 0051)

- `job_asset_processing_states` — UNIQUE(job_id, asset_id)
- `processing_attempts` — UNIQUE(job_id, asset_id, strategy, attempt_number)

## API

Additive `JobSummary.asset_progress` from `result_json.asset_progress`.

## Out of scope

QR/barcode/OCR, per-image fallback, frontend reprocess actions, prompt changes.
