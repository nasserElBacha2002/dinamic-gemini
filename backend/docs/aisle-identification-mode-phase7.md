# Aisle identification — Phase 7 (operational UX per image)

## Enable / rollback

```env
PROCESSING_OBSERVABILITY_ENABLED=false      # master switch for read APIs + UX tab
PROCESSING_ASSET_LOGS_UI_ENABLED=false      # structured events timeline
PROCESSING_ASSET_REPROCESS_ENABLED=false    # reprocess / retry / send-to-external
PROCESSING_MANUAL_ACTIONS_ENABLED=false     # invalidate (+ enhanced manual gates)
PROCESSING_EVENTS_PERSISTENCE_ENABLED=false # write ProcessingEvent rows
```

| Flag | Effect |
|------|--------|
| All `false` (default) | Pipeline unchanged; capabilities endpoint reports UX off; legacy observability tab remains |
| `PROCESSING_OBSERVABILITY_ENABLED=true` | List/detail/events read APIs + Procesamiento tab |
| Reprocess / manual flags | Gate mutations independently |

Rollback: set flags to `false`. Attempts, states, and events rows are **not** deleted.

Capabilities: `GET /api/v3/config/processing-observability-capabilities`

## Source of truth

UI derives from persisted contracts (not log parsing):

- `job` + `engine_params_json.identification_execution`
- `job_asset_processing_states`
- `processing_attempts`
- `external_image_analysis_requests`
- `processing_events` (optional)
- active position / manual coverage
- profile snapshot on the job (Phase 6)

One image → at most one active position. Attempts are immutable; reprocess does not wipe history.

## APIs

| Method | Path | Notes |
|--------|------|-------|
| GET | `.../jobs/{jobId}/assets/processing` | Paginated operational list + progress summary |
| GET | `.../jobs/{jobId}/assets/{assetId}/processing-detail` | Detail + attempts + evidence hashes + actions |
| GET | `.../assets/{assetId}/processing-events` | Paginated structured events |
| GET | `.../assets/{assetId}/processing-events/export?format=jsonl\|csv` | Sanitized download |
| POST | `.../assets/{assetId}/reprocess` | Queue PENDING; `Idempotency-Key`; `expected_state_version` |
| POST | `.../assets/{assetId}/retry-persistence` | Reprocess as `EXTERNAL_PROVIDER` (reuse durable result when worker supports it) |
| POST | `.../assets/{assetId}/send-to-external` | Same queue with external strategy |
| POST | `.../assets/{assetId}/invalidate-result` | Soft invalidate → `PENDING_MANUAL_REVIEW` |
| POST | existing `.../manual-result` | Unchanged Phase 2+ flow |

Concurrency conflict → `409 ASSET_PROCESSING_STATE_CONCURRENCY_CONFLICT`.

## Reprocess policy

1. Resets asset state to `PENDING` with optimistic version bump.
2. Does **not** delete attempts, external requests, or events.
3. Does **not** restart the whole aisle.
4. Execution is picked up by an active job worker, or left PENDING for a follow-up single-asset runner (finished jobs may need that runner — see limitations).
5. Manual overwrite requires explicit `manual_policy` confirmation in the UI dialog.

## Events

Migration `0059_processing_events.sql` / `schema.sql` table `processing_events`.

Only operational events are written when `PROCESSING_EVENTS_PERSISTENCE_ENABLED=true`. Metadata is sanitized (no API keys, prompts, full OCR text, paths, tokens).

## Historical jobs

Jobs without per-asset states/attempts return `historical_incomplete=true` and empty timelines — no invented data.

## Limitations

- Per-asset reprocess queues state; a dedicated post-job single-asset executor is not fully wired for all terminal job statuses.
- Fine-grained RBAC (`view_sensitive_evidence`, etc.) is capability/flag gated under admin auth; conceptual permission split is documented for a later auth pass.
- Bounding-box overlays require persisted regions; UI does not invent boxes.
- Phase 6 profile editing is not available from the operational drawer (snapshot + navigation only).
