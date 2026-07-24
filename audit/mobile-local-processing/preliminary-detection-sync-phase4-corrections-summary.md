# Phase 4 corrections — decisions & limitations

## Decisions

1. **Retry scheduling:** Single JS timer via `getEarliestSyncRetryAt` + reschedule after every `syncPending`; connectivity `online` triggers sync. No per-draft timers.
2. **Background flag removed:** `preliminaryDetectionBackgroundSync` / `DINAMIC_FLAG_PRELIMINARY_BG_SYNC` deleted. WorkManager preliminary worker is **not** implemented; limitation is explicit.
3. **SQL races:** `INSERT` + catch unique violation → re-read → canonical compare → duplicate/conflict (never 500).
4. **Canonical content:** `PreliminaryDetectionContentCanonicalizer` is the single comparison source.
5. **Secondary key:** same payload → duplicate (returns canonical draft_id + requested_draft_id); divergent → CONFLICT.
6. **Error codes:** `StructuredApiHttpError` with `PRELIMINARY_*` codes; mobile classifies by `code`, not message text.
7. **NOT_READY:** explicit `NOT_READY_ASSET|SESSION|CLIENT_FILE`; irreparable → `INVALID_LOCAL_DRAFT` / FAILED_TERMINAL.
8. **detected_at:** SQLite v11 column; set once at scan completion; sync sends `detected_at`, not `updated_at`.
9. **Lease:** 90s lease vs 30s request timeout.
10. **Retention:** backend `expires_at` (+90d) + `delete_expired`; mobile purge SYNCED 14d / terminal 30d.
11. **Migration 0062:** forward-only; disable via `SERVER_PRELIMINARY_DETECTION_INGEST=false`. Formal DROP documented for non-prod.

## Test results (this run)

| Area | Result |
|------|--------|
| Backend unit + API | 17 passed, 3 SQL skipped (no ODBC driver / table) |
| Mobile typecheck/lint | PASS |
| Mobile preliminary tests | 12 passed |
| SQL Server live | SKIPPED (ODBC Driver 18 missing locally) |
| Gradle / expo-doctor / full E2E device | NOT RUN |

## Remaining limitations

- Live SQL Server migration upgrade/rollback not executed in this environment.
- Concurrent insert stress against real SQL not executed (typed unique handling covered in unit + insert-duplicate SQL test when DB available).
- Full scan→upload→sync→process device E2E not run.
- WorkManager background sync intentionally deferred.
