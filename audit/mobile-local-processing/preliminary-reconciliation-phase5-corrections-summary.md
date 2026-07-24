# Phase 5 corrections — summary of decisions

## Decisions

1. **Server-side enqueue on job terminal** via `try_enqueue_preliminary_reconciliations` after `finalize_success` / `finalize_code_scan_success`. Independent of mobile UI flags.
2. **Worker** `PreliminaryReconciliationWorker` claims PENDING/RETRY_SCHEDULED with lease; POST returns **202** and only enqueues.
3. **Identity** `UNIQUE(preliminary_detection_id, comparison_version, job_id)` — reprocess (new job) creates new rows; migration **0064**.
4. **No blind overwrite** — unique race re-reads; terminal rows immutable; CAS via `row_version`.
5. **Snapshot filter** — only `job_source_assets` asset IDs.
6. **GLOBAL_BATCH** — ignores prior CODE_SCAN attempts; requires structured global evidence.
7. **Multiple remote semantics** — `(code, quantity, status)` distinct → NOT_COMPARABLE.
8. **Job authority** — only SUCCEEDED comparable; FAILED/CANCELED/TIMED_OUT → dedicated reasons.
9. **Remote version required** — missing → NOT_COMPARABLE_VERSION_UNKNOWN.
10. **Mobile** — view vs trigger flags; map by `server_preliminary_id` / `preliminary_detection_id` + `job_id` filter.
11. **Metrics** — SQL `aggregate_metrics`; no `limit=5000` list scan.

## Limitations remaining

- Live SQL Server upgrade / concurrent race / E2E device matrix not executed in this environment (no ODBC/`jwt` for full API app import in local venv).
- Android gradle / expo-doctor / assembleRelease not run.
- Shared cross-language fixture file not fully wired into CI.
- Inline process on POST remains opt-in (`process_inline_limit=0`).
