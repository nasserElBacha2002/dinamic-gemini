# Mobile Observability Phase 0 — Implementation Report

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`

## Summary

Phase 0 instruments the existing mobile capture → prepare → upload → `/process` → job-monitor path with a kill-switchable observability stack. No server pipeline, CODE_SCAN, OCR, compression parameters, concurrency, endpoints, or functional UI states were changed. With `DINAMIC_FLAG_UPLOAD_OBS=0`, producers receive a `NoOpObservabilityReporter` and operational behavior matches the pre-Phase-0 path.

## Architecture

```text
CaptureService / UploadQueue / ProcessingService / JobMonitor
        │
        ▼
ObservabilityReporter (interface)
        │
        ├── Flagged + Safe wrappers
        ├── BufferedSqliteObservabilityReporter  → observability_events (SQLite v5)
        └── StructuredObsLogReporter             → existing Logger ring buffer
        │
        ▼
Baseline export (p50/p95) via DiagnosticScreen / diagnostic JSON
```

**Decisión:** Reuse `Logger` + SQLite instead of a third-party analytics SDK.  
**Evidencia:** Existing `mobile/src/core/logging.ts` redaction + ring buffer; no analytics dependency in `package.json`.  
**Implementación:** `SafeObservabilityReporter` + buffered SQLite flush; failures never throw to callers.  
**Riesgo:** Events can be lost if process dies before flush (~1.5s / 12 events).  
**Mitigación:** Flush on dispose; 14-day prune; diagnostic export reads persisted rows.  
**Validación:** Unit tests for Safe/NoOp/flag; full mobile `npm test` green.

## Decisions (selected)

### Feature flag default ON

**Decisión:** `uploadObservabilityEnabled` defaults to true (`DINAMIC_FLAG_UPLOAD_OBS !== '0'`).  
**Evidencia:** Phase 0 goal is to collect a baseline; kill switch remains available.  
**Implementación:** `featureFlags.ts`, `app.config.ts`, `mobile/.env.example`.  
**Riesgo:** Slight SQLite/log overhead when enabled.  
**Mitigación:** Buffered writes; NoOp when disabled.  
**Validación:** Flag unit tests; factory returns NoOp when `enabled: false`.

### `originalSize` accuracy in prepare

**Decisión:** Persist true pre-transform bytes as `originalSize` (previously the prepared size was incorrectly returned as original).  
**Evidencia:** `photoPrepare.ts` mutated `size` then assigned `originalSize: size`.  
**Implementación:** Capture `originalSize` after empty-check; return prepared `size` separately; add profile/dimensions metadata.  
**Riesgo:** `capture_photos.original_size` values become meaningful; packing still uses `upload_size`.  
**Mitigación:** Upload packing unchanged (`prepared.size` / `upload_size`).  
**Validación:** Typecheck + existing upload/processing tests.

### First server result approximation

**Decisión:** Emit `capture_to_first_server_result` when aisle `positions_count > 0` or on terminal status.  
**Evidencia:** Job poll only returns aisle status + job status, not incremental merge rows.  
**Implementación:** `JobMonitor.pollOnce` with `approximated` attribute when terminal with zero positions.  
**Riesgo:** May under/over-estimate “first result” vs web merge-results.  
**Mitigación:** Documented limitation; attribute `approximated`.  
**Validación:** Code path + catalog docs.

## Instrumented points

| Stage | Events (examples) |
| ----- | ----------------- |
| Session | `session.created` |
| Queue | `photo.queued`, `queue.restored` |
| Prepare | `photo.prepare_started`, `photo.prepare_completed`, `photo.prepare_failed` |
| Upload | `photo.upload_*`, `batch.upload_*`, `session.first_upload_started`, `session.all_uploads_completed` |
| Process | `session.process_requested`, `session.process_accepted`, `session.process_failed` |
| Job | `job.started_observed`, `session.capture_to_first_server_result`, `session.job_terminal`, `job.poll_failed` |

## Correlation IDs

Reused existing identifiers: `session_id`, `client_file_id`, `upload_batch_id`, `backend_job_id` (as `serverJobId`), local `processing_jobs.id` (as `localJobId`), plus generated `attemptId` for upload/process attempts.

## Security / privacy

Sanitize strips URI/path/filename/token/OCR/qty/SSID/IP/etc. Events carry technical metadata only. Diagnostic export continues to omit tokens/photos/API keys; baseline nested under `observabilityBaseline`.

## Persistence

Migration **v5** `observability_events` with indexes on `created_at`, `session_id`, `name`, `client_file_id`. Retention prune: 14 days (best-effort on stack create).

## Feature flag

- Name: `uploadObservabilityEnabled` / env `DINAMIC_FLAG_UPLOAD_OBS`
- Kill switch: set to `0`

## Files changed (high level)

- `mobile/src/observability/**` — new module
- `mobile/src/database/migrations/migrations.ts` — v5
- `mobile/src/features/upload/{uploadQueue,photoPrepare}.ts`
- `mobile/src/features/processing/{processingService,jobMonitor}.ts`
- `mobile/src/features/capture/captureService.ts`
- `mobile/src/runtime/bootstrap/createAppServices.ts`
- `mobile/src/features/support/diagnosticExport.ts`
- `mobile/src/screens/DiagnosticScreen.tsx`
- `mobile/src/core/featureFlags.ts`, `app.config.ts`, connectivity, tests, README

## Limitations

### [HIGH] Samsung S10+ manual baseline not executed in this environment

**Contexto:** Acceptance criteria require device runs (20/50 wifi/cellular, HEIC, reconnect, etc.).  
**Impacto:** No real p50/p95 device numbers in the test report.  
**Motivo:** Implementation ran in CI/dev host without the release device attached.  
**Próximo paso:** Run release build scenarios and paste metrics into the test report.

### [MEDIUM] First-result timing may be approximated

**Contexto:** Polling aisle status lacks merge-result streaming.  
**Impacto:** `capture_to_first_server_result_ms` may equal terminal time when positions stay 0 until completion.  
**Motivo:** No functional polling/API change allowed in Phase 0.  
**Próximo paso:** Optional later hook when merge-results first becomes non-empty (still no poll-rate change if event-driven from existing poll).

### [LOW] Buffered SQLite may drop trailing events on hard kill

**Contexto:** Flush interval 1.5s / batch 12.  
**Impacto:** Last few events before process death may be missing.  
**Motivo:** Non-blocking requirement.  
**Próximo paso:** Call `dispose()` flush on background transitions if needed.

## Behavior changes

- Functional upload/process/retry/endpoints: **none intentional**.
- Metadata: `original_size` now reflects pre-transform bytes (correctness for metrics).
- Diagnostic JSON gains `observabilityBaseline` when store present.
- New diagnostic button for baseline share.

## Validation

- `npm test` (core + services + integration): pass
- `npm run typecheck`: pass
- Manual S10+: **not run** (limitation above)
