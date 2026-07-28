# ADR — Job lease fencing and stale worker rejection

## Status

Accepted (Phase 3 — **PARTIAL** implementation, 2026-07-28)

## Context

Phase 1 introduced atomic STARTING→RUNNING claiming with a dedicated `claim_owner_id`, so two workers cannot both obtain `may_execute=True` for the same attempt. That does **not** stop a worker that already claimed the job from continuing to write after:

- heartbeat timeout / process pause,
- network partition,
- a future recovery path that reassigns the running row.

Unfenced `save()` / `merge_result_json` / terminal transitions allow **stale writers** to corrupt `result_json` or race terminal status. Audit / Phase 1 ADR explicitly deferred fencing tokens and lease stealing to Phase 3+.

## Decision

1. Introduce domain types in `backend/src/domain/jobs/lease.py`:
   - `JobLease` (owner + monotonic `fencing_token` + expiry),
   - `LeaseWriteOutcome` / `LeaseRenewalOutcome` + result wrappers,
   - `JobLeaseLostError` for cooperative halt (**do not** mark job FAILED).
2. Additive migration **`0072_inventory_jobs_lease_fencing.sql`**:
   - `lease_fencing_token`, `lease_expires_at`, `lease_acquired_at`,
   - index `IX_inventory_jobs_lease_expiry`,
   - **reuse** `claim_owner_id` as lease owner (no duplicate owner column).
3. Config via env (no hardcoded durations in call sites beyond defaults in settings):
   - `JOB_LEASE_DURATION_SEC`,
   - `JOB_LEASE_HEARTBEAT_INTERVAL_SEC`,
   - `JOB_LEASE_RENEWAL_SAFETY_MARGIN_SEC` (defined; urgency consumption deferred).
4. Extend `JobRepository` (SQL + memory):
   - claim acquires lease + increments token,
   - `renew_lease` / `touch_heartbeat_if_leased` CAS (token unchanged),
   - `reacquire_expired_lease` steal (token +1) for controlled recovery/tests,
   - `merge_result_json_if_leased`, `assert_lease`, `complete_if_leased`, `fail_if_leased`.
5. Worker wiring:
   - prep returns `lease`,
   - monitoring renews with fencing; lease loss → `runtime_abort` without FAIL,
   - executor passes lease into finalization / code_scan and protected merges,
   - `JobLeaseLostError` halts execution.
6. Observability: structured logs `event=job_lease_*` and `event=job_stale_write_rejected`. **No** Prometheus counters in this phase.
7. Explicitly **out of this ADR’s completed scope**: cancel fencing, artifact outbox fencing, operational promotion fencing, production steal scheduler, Phase 4.

## Consequences

- Stale workers lose renew/merge/complete/fail races against a newer fencing token.
- Lease loss is observable and non-destructive to job status (another owner may continue; or Phase 1 stale-fail may still apply later).
- Requires migration 0072 before SQL IT / production deploy of lease-aware code.
- Gaps remain: unfenced cancel/artifacts/promotion; steal API not wired to prod recovery; safety margin setting unused; metrics limited to logs.
- Mergeability is **conditional** until gaps are accepted or closed (see `implementation-report.md` §28).

## Alternatives considered

- **Ownership = heartbeat only** without fencing token — rejected; same owner string after steal would not invalidate in-memory leases of the loser if token did not change.
- **Separate `lease_owner_id` column** — rejected; reusing `claim_owner_id` keeps one ownership identity.
- **Fail job on lease loss** — rejected; would fight with a valid new owner mid-run.
- **In-memory-only fencing** — rejected for production multi-process workers; memory adapter mirrors contract for tests/dev only.
- **Prometheus-first metrics** — deferred; structured logs ship first.
