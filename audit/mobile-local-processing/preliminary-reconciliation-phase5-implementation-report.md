# Preliminary reconciliation — Phase 5 implementation report

## Status

`IMPLEMENTED_WITH_LIMITATIONS`

## Architecture

```text
local CODE_SCAN draft (synced)
  → asset_id / client_file_id
  → JobAssetProcessingState + ProcessingAttempt (per asset)
  → ResolveComparableRemoteResult
  → compare_preliminary_vs_remote
  → preliminary_detection_reconciliations
  → GET list + metrics (read-only)
```

Layers:

| Concern | Location |
|--------|----------|
| Mapping resolution | `resolve_comparable_remote_result.py` |
| Normalization + compare | `preliminary_detection_compare.py` |
| Orchestration | `ReconcilePreliminaryDetectionsUseCase` |
| Metrics aggregates | `list_preliminary_reconciliations.py` |
| Persistence | `preliminary_detection_reconciliations` table + repos |
| API | `preliminary_reconciliations.py` (POST trigger + GET list) |
| Mobile diagnostic | `ReconciliationQueryService` + ProcessingScreen |

Comparison is **not** in routers, ORM, JobMonitor (beyond trigger), UI, or SQL repos.

## Mapping

Reliable path (CODE_SCAN / per-asset attempts):

```text
draft.asset_id → state(job, asset) → attempts(job, asset).normalized_result
```

`NOT_COMPARABLE` reasons include:

- `NOT_COMPARABLE_NO_ASSET_MAPPING`
- `NOT_COMPARABLE_GLOBAL_BATCH`
- `NOT_COMPARABLE_MULTIPLE_REMOTE_RESULTS`
- `NOT_COMPARABLE_MISSING_REMOTE_EVIDENCE`
- `NOT_COMPARABLE_VERSION_UNKNOWN`
- `NOT_COMPARABLE_REMOTE_NOT_TERMINAL` / `JOB_NOT_TERMINAL` (retryable)
- `NOT_COMPARABLE_LOCAL_NOT_TERMINAL`

**No** order / array-index / time-proximity matching.

## Outcomes

Full Phase 5 outcome set (code + quantity variants, ambiguous, not comparable).  
Quantity compared only when codes match. Leading zeros preserved; no case fold.

## Worker

Preference “job terminal → enqueue → worker” is implemented as:

1. Mobile `JobMonitor` (flag on) calls `POST …/reconcile-preliminary-detections` after terminal job.
2. Use case processes a batch (default 50) synchronously and persists rows.

**Limitation:** no separate multi-worker lease process / cron daemon yet. Idempotent POST + `RETRY_SCHEDULED` rows support a future worker.

## Persistence

Migration `0063_preliminary_detection_reconciliations.sql` — separate table, unique `(preliminary_detection_id, comparison_version)`, FKs, indexes. Forward-only documented.

## Security

- Routes under admin-authenticated v3 inventories router.
- Aisle scoped to inventory via `require_aisle_scoped_to_inventory`.
- Mobile never posts computed outcomes; server compares.
- Flags default **false**.

## Metrics

Named as **server agreement proxies** (`server_agreement_rate`, FP/FN proxies).  
`NOT_COMPARABLE` excluded from precision denominators.  
Human ground-truth accuracy **not** claimed.

## Limitations

- Live SQL Server migration / concurrent insert tests not run in this environment.
- API route tests not executed (local venv missing `jwt`).
- Session filter on GET not implemented (capture_session_id not on preliminary table).
- No dedicated background reconciliation worker process.
- Manual labeled ground-truth metrics dataset not produced.
- Web diagnostic UI not added (mobile diagnostic only).
