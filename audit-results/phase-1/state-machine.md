# Phase 1 — Job / aisle state machine

## Job statuses (v3 `inventory_jobs`)

| Estado actual | Evento | Estado siguiente | Actor | Condición |
|---|---|---|---|---|
| *(create)* | launch / retry | `STARTING` | API | new attempt row |
| `QUEUED` | `claim_next_queued_job` | `STARTING` | poll worker | SQL UPDLOCK / memory lock |
| `STARTING` | `try_claim_starting_to_running` | `RUNNING` | worker | CAS `status='starting'`; sets `claim_owner_id` |
| `RUNNING` | claim retry same `claim_owner_id` | `RUNNING` | same owner | idempotent `ALREADY_OWNED` |
| `RUNNING` | claim other / null owner | `RUNNING` | other worker | `CONFLICT` (no mutate) |
| `RUNNING` | heartbeat | `RUNNING` | owner | status still active |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | success finalize | `SUCCEEDED` | owner | terminal path |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | fail | `FAILED` | owner / recovery | CAS where implemented |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | stale reclaim | `FAILED` | recovery | single TX job+aisle |
| `CANCEL_REQUESTED` | cancel before start | `CANCELED` | preparation | |
| Terminal | any claim | unchanged | — | `TERMINAL` / reject |

## Aisle statuses (processing)

| Job event | Aisle effect |
|---|---|
| Claim acquired | `QUEUED` / `ASSETS_UPLOADED` / `PROCESSING` → `PROCESSING` (same TX on SQL) |
| Claim aisle missing / terminal / mismatch | Job claim rolled back; outcomes `TARGET_*` |
| Stale reclaim won | If no other active job for aisle and aisle in `QUEUED`/`PROCESSING` → `FAILED` (`STALE_JOB`) |
| Other active job exists | Aisle unchanged; log `job_aisle_state_inconsistency` |
| Terminal aisle | Not reactivated by reclaim or claim |

## Invariants

1. At most one worker with `may_execute=True` per job attempt (except same-owner idempotent retry).
2. CAS loser never executes the pipeline.
3. Null `claim_owner_id` never proves ownership.
4. Job `RUNNING` after successful claim implies aisle `PROCESSING` for aisle-targeted jobs (committed together).
5. Stale job + aisle reconcile in one transaction; aisle not failed if another active job exists.
6. `attempt_count` changes only when a **new job row** is created.
7. `started_at` is not reset on idempotent same-owner claim.

## Claim outcomes

`acquired` | `already_owned` | `conflict` | `not_found` | `terminal` | `invalid_status` | `target_not_found` | `target_mismatch` | `target_invalid_status`

`may_execute` = `acquired` ∨ (`already_owned` with matching non-null `claim_owner_id`).
