# OEM / background restrictions

## Phase 2 WorkManager (corrected)

When `backgroundUploadWorker` is enabled:

- Android WorkManager runs a **single** unique work: `dinamic-upload-queue`.
- Only **prepared** photos are uploaded natively (prepare stays in JS).
- Tokens are mirrored to **EncryptedSharedPreferences only** (no plaintext fallback). If the vault is unavailable, the worker does not upload (`AUTH_VAULT_UNAVAILABLE`).
- Foreground progress uses `CoroutineWorker.setForeground` when `backgroundUploadForegroundService` is on (no duplicate Upload FGS).
- WorkManager `SystemForegroundService` must declare `foregroundServiceType="dataSync"` (Android 12+); otherwise the app crashes on the first upload foreground promote.
- Notification action **Pausar cola** cancels WorkManager + in-flight OkHttp and persists pause.
- `allowMobileDataUploads=false` → `NetworkType.UNMETERED`; preference changes reschedule with REPLACE.
- `backgroundUploadRebootResume=false` → BootReceiver cancels persisted upload work after reboot.
- When all photos of a session are uploaded, native posts idempotent `POST /process`.

When flags are off: recovery remains **app reopen → SQLite + JS UploadQueue**.

## Samsung / OEM honesty

Do **not** promise unlimited background execution.

- Doze / App Standby / battery saver may delay work.
- Force-stop prevents WorkManager until the user opens the app again.
- Swipe-away ≠ force-stop (behavior varies by OEM).
- UI copy: *“La carga continuará en segundo plano cuando Android lo permita.”*

## Operator tips

1. Apps → Dinamic Captura → Battery → Unrestricted (if available).
2. Allow notifications.
3. Reopen the app and use **Diagnóstico** if the queue stalls (including after 413 reprepare).

## Work ownership names

- `dinamic-upload-queue` — sole upload drain (session schedule aliases map here)
- Legacy `dinamic-upload-session-*` names are accepted but do **not** enqueue a second worker
