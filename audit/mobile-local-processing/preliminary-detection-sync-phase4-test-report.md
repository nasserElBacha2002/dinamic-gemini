# Phase 4 — Preliminary detection sync — test report

## Mobile

| Suite | Result |
|-------|--------|
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm run test:core -- --testPathPattern=featureFlags` | PASS (10) |
| `npm run test:services -- --testPathPattern=preliminaryDetectionSyncService` | PASS (9) |

Covered: flag off, missing asset, success, 422, 409, 500, 404, 403, enqueue after upload.

### Not executed (mobile)

- Full `test:integration`
- `npx expo-doctor`
- Device / Samsung matrix
- Dedicated WorkManager preliminary-sync worker path

## Android / Gradle

Not executed in this run (module unit tests / assembleRelease deferred).

## Backend

| Suite | Result |
|-------|--------|
| `pytest backend/tests/application/use_cases/test_upsert_preliminary_detection.py` | PASS (11) |
| `ruff check` (new Phase 4 files) | PASS |

Covered: disabled flag, create, idempotent repeat, content conflict, missing asset, wrong aisle, client_file mismatch, validation (code/hash/ambiguous), cross-draft hash dedupe.

### Not executed (backend)

- SQL Server live migration upgrade / rollback
- SQL repository integration tests against real DB
- Concurrent insert stress
- Full API route integration with TestClient + auth
- End-to-end: scan → upload → sync → /process

## Migrations

- File added: `backend/src/database/migrations/versions/0062_mobile_preliminary_detections.sql`
- Mobile SQLite migration v10 (sync columns)
- Live apply not run here

## Scenarios not executed

- Sync down but `/process` still works (manual E2E)
- Retry after reboot / process death
- 100 drafts batch
- Token expiry mid-sync
- Multi-session parallel sync
- App closed + WorkManager-only sync
