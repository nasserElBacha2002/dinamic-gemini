# Mobile Upload Phase 1 — Implementation Corrections

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`  
**Date:** 2026-07-23

## Architectural decisions

1. **UploadSlotGate** — slots are acquired synchronously in `tick()` before `void uploadPreparedBatch(...)`. Release is exactly-once in batch `finally` (or immediately if no batch can be packed).
2. **Cancel vs cleanup** — `cancelPhoto()` records intent, aborts transport when enabled, marks `excluded`, and defers transform deletion to `pendingTransformCleanup` flushed after request settlement.
3. **Late success** — cancelled photos that still receive `uploaded` from the server are never promoted to `uploaded`; they go through `reconcileCancelledRemoteAsset` (`remote_delete_pending` → delete → `remote_deleted`, or stay pending on delete failure).
4. **Error codes** — `ApiClient` emits `REQUEST_ABORTED` / `REQUEST_TIMEOUT` / `NETWORK_ERROR`; `UploadQueue` classifies by code (no message substring matching).
5. **Session profile** — SQLite migration v6 adds `preparation_processing_mode` (default `UNKNOWN`). UI / `startProcess` persist mode; prepare resolves profile from the session row. `/process` body unchanged.
6. **Feature flags** — Phase 1 flags default **off in production**, **on in development/staging**; independent env overrides via tri-state in `app.config.ts`.

## Validation (executed)

| Command | Result |
| --- | --- |
| `npm run lint` | pass |
| `npm run typecheck` | pass |
| `npm test` (core + services + integration) | pass (209 tests) |
| `npx expo-doctor` | 16/17 — pre-existing Xcode 26 vs Expo 51 advisory |

## Not executed (explicit limitations)

- Release APK build on device
- Samsung S10+ matrix (20/50/100 Wi‑Fi, cellular, HEIC, cancel, disconnect, retry, remote CODE_SCAN / INTERNAL_OCR)
- Byte/time/memory comparison numbers vs baseline

## Rollback

Disable independently or leave production defaults off:

- `DINAMIC_FLAG_UPLOAD_DIM_CAP`
- `DINAMIC_FLAG_UPLOAD_ADAPTIVE_QUALITY`
- `DINAMIC_FLAG_UPLOAD_ADAPTIVE_CONCURRENCY`
- `DINAMIC_FLAG_UPLOAD_ABORT`

With all Phase 1 flags off: legacy quality, concurrency cap 2, no proactive dimension cap, no multipart abort on cancel.
