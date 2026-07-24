# Mobile Background Upload Phase 2 — Implementation Report

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`  
**Date:** 2026-07-23

## Architecture

```text
Capture → JS photoPrepare → SQLite (prepared)
→ WorkManager (DinamicUploadWorker) and/or JS UploadQueue
→ POST /assets (unchanged)
→ POST /process (unchanged) → server pipeline
```

| Layer | Role |
| --- | --- |
| SQLite | Source of truth for queue + leases |
| JavaScript | Prepare images, UI, observe, schedule work, foreground drain with leases |
| WorkManager | Schedule/recover durable upload when process is gone |
| Upload FGS | Visible notification for long native drains |
| AuthVault | EncryptedSharedPreferences mirror of tokens + API config |

## Ownership / leases

Columns (migration **v7**):

- `upload_worker_owner` (`js` | `native`)
- `upload_lease_token`
- `upload_lease_expires_at`
- `upload_heartbeat_at`
- `upload_cancel_requested`

Transactional acquire in JS (`CaptureRepository.tryAcquireUploadLease`) and Kotlin (`UploadSqliteStore.tryAcquireLease`). Foreign active leases are skipped by the other owner.

## WorkManager

- Unique work: `dinamic-upload-queue`, `dinamic-upload-session-{sessionId}`
- Policy: `ExistingWorkPolicy.KEEP`
- Network constraint: `CONNECTED`
- Exponential backoff
- Worker opens Expo SQLite DB paths, uploads prepared files only (no HEIC/resize in native)

## Foreground Service

- `UploadForegroundService` (channel `dinamic_upload_fgs`, id 42002)
- Promoted from worker when `backgroundUploadForegroundService` is on
- Stopped when worker finishes
- Copy: honest OEM wording (“cuando Android lo permita”)

## Auth

- On login/refresh/saveTokens → sync to `AuthVault`
- On logout → cancel work + clear vault + pause queue
- Worker: 401 → refresh → retry; definitive failure → `AUTH_REQUIRED` (pause until login)

## Feature flags (prod opt-in)

| Flag | Env |
| --- | --- |
| `backgroundUploadWorker` | `DINAMIC_FLAG_BG_UPLOAD_WORKER` |
| `backgroundUploadForegroundService` | `DINAMIC_FLAG_BG_UPLOAD_FGS` |
| `backgroundUploadRebootResume` | `DINAMIC_FLAG_BG_UPLOAD_REBOOT` |

Flags off → legacy JS queue only (no native schedule).

## Server contracts

Unchanged: `POST /assets`, `POST /process`, CODE_SCAN / INTERNAL_OCR / fallback remain server-side. No local OCR/barcode.

## Samsung / OEM limits

Documented in `mobile/docs/OEM_BACKGROUND.md` (updated). No unlimited background guarantee.

## Limitations

See test report. Device release matrix and full Gradle module unit tests pending where `android/` is not prebuilt in this environment.
