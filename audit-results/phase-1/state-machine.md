# Phase 1 — Job / aisle state machine

## Job statuses (v3 `inventory_jobs`)

| Estado actual | Evento | Estado siguiente | Actor | Condición |
|---|---|---|---|---|
| *(create)* | launch / retry | `STARTING` | API | new attempt row |
| `QUEUED` | `claim_next_queued_job` | `STARTING` | poll worker | SQL UPDLOCK / memory lock |
| `STARTING` | `try_claim_starting_to_running` | `RUNNING` | worker | CAS `status='starting'` |
| `RUNNING` | claim retry same `execution_id` | `RUNNING` | same owner | idempotent `ALREADY_OWNED` |
| `RUNNING` | claim other `execution_id` | `RUNNING` | other worker | `CONFLICT` (no mutate) |
| `RUNNING` | heartbeat | `RUNNING` | owner | status still active |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | success finalize | `SUCCEEDED` | owner | terminal path |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | fail | `FAILED` | owner / recovery | CAS where implemented |
| `RUNNING`/`STARTING`/`CANCEL_REQUESTED` | stale reclaim | `FAILED` | recovery | heartbeat age ≥ threshold |
| `CANCEL_REQUESTED` | cancel before start | `CANCELED` | preparation | |
| Terminal | any claim | unchanged | — | `TERMINAL` / reject |

## Aisle statuses (processing)

| Job event | Aisle effect |
|---|---|
| Claim acquired | `QUEUED` / `ASSETS_UPLOADED` / `PROCESSING` → `PROCESSING` (same TX on SQL) |
| Stale reclaim won | If no other active job for aisle and aisle in `QUEUED`/`PROCESSING` → `FAILED` (`STALE_JOB`) |
| Other active job exists | Aisle unchanged; log `job_aisle_state_inconsistency` |
| Terminal aisle (`PROCESSED`, …) | Not reactivated by reclaim |

## Invariants

1. At most one successful `STARTING→RUNNING` CAS per job.
2. If `job.status = RUNNING` after claim, aisle should be `PROCESSING` (reconciled on `ALREADY_OWNED` if partial failure left aisle queued).
3. Stale fail of job J does not fail aisle if another job for the same aisle is still `STARTING`/`RUNNING`/`CANCEL_REQUESTED`.
4. `attempt_count` changes only when a **new job row** is created for a new attempt.

## Claim outcomes

`acquired` | `already_owned` | `conflict` | `not_found` | `terminal` | `invalid_status`

`may_execute` = `acquired` ∨ `already_owned`.
