# Phase 2 — Upload state machine

## Photo upload statuses (persisted)

```text
not_queued
→ queued
→ preparing
→ queued (prepared: upload_size set)
→ uploading   (lease held by js|native)
→ uploaded

Alternates:
queued|retryable_error → retryable_error (next_retry_at)
* → permanent_error
* → excluded
uploading + cancel → excluded | remote_delete_pending (late success)
```

## Lease overlay

```text
no lease
→ acquire (owner, token, expires_at)
→ heartbeat / renew
→ release on terminal status or expiry reclaim
```

Invariant: at most one active non-expired lease owner per photo.

## Cancel

```text
UPLOADING + cancel
→ upload_cancel_requested=1
→ abort transport (if flag)
→ excluded (JS) or settlement in worker
→ if late HTTP success: remote_delete_pending + delete asset
```

## Recovery

```text
process death / reboot
→ WorkManager reschedules (if worker flag on)
→ worker acquires expired/empty leases
→ uploads prepared rows only
→ unprepared rows wait for JS prepare
```

## Events (observability)

JS continues Phase 0 events. Native schedules are logged; JS emits `queue.restored` / upload events when the app is active.
