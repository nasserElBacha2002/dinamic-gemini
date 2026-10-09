# Phase 2 Implementation (corrections applied)

## Delivered

- Single unique WorkManager queue: `dinamic-upload-queue` (no duplicate session+global workers).
- Foreground owned only by `CoroutineWorker.setForeground` (UploadForegroundService removed).
- Encrypted-only `AuthVault` (no plaintext SharedPreferences fallback); `AUTH_VAULT_UNAVAILABLE` blocks uploads.
- Notification action **Pausar cola** cancels WorkManager + OkHttp + persists pause.
- Network constraints: `CONNECTED` vs `UNMETERED` from `allowMobileDataUploads`; reschedule on change.
- `backgroundUploadRebootResume`: BootReceiver cancels persisted work when flag/worker is off.
- HTTP 413 → `UPLOAD_REPREPARE_REQUIRED` (clears transform/size; no same-file retry loop).
- Lease heartbeat during long uploads; abort if ownership lost.
- When all session photos are uploaded → idempotent `POST /process` (`mobile-process:{sessionId}`).
- Schema gate: require migration ≥ 7 (`DB_MIGRATION_REQUIRED`).
- Classified transport errors: timeout, cancel, TLS, file missing, parse, network.

## Honest limitations

- Prepare (HEIC/resize) remains JS-only; 413 reprepare waits for app open.
- Vault/keystore failure leaves queue pending until app opens with working crypto.
- OEM/Samsung may delay or kill background work — UI does not over-promise.
- Full device release matrix (Samsung S10+) is tracked separately; not assumed green without evidence.

## Validation

```bash
cd mobile
npm run typecheck && npm run lint && npm test
# Android (after prebuild):
cd android && ./gradlew :capture-foreground-service:test lint
```
