# ADR — Atomic job claiming and stale aisle reconciliation

## Status

Accepted (Phase 1 — 2026-07-28)

## Context

Technical audit v2 identified two P0 issues:

1. **Double job execution** — `V3JobExecutionStateService.mark_running` used get/mutate/save without a compare-and-set predicate on `status`.
2. **Stale reclaim inconsistency** — bulk `reclaim_stale_running_jobs` failed jobs without reconciling the related aisle, leaving aisles in `PROCESSING`/`QUEUED`.

The on-demand path creates jobs as `STARTING` and spawns a worker; `QUEUED → STARTING` SQL claim already used `UPDLOCK`. The race lived in `STARTING → RUNNING`.

## Decision

1. Introduce explicit claim outcomes (`JobClaimOutcome`) and `JobClaimResult`.
2. Implement `JobRepository.try_claim_starting_to_running` with SQL `UPDATE … WHERE status = 'starting'` (rows_affected) and a memory lock that mirrors the same contract.
3. When `aisle_id` is provided, mark the aisle `processing` in the **same SQL transaction** as the successful claim.
4. Ownership token = existing `Job.execution_id` (no new columns / no migration).
5. Stale policy remains **Option C**: active stale jobs → `FAILED` / `STALE_JOB`, then reconcile aisle only if no other active job targets the same aisle.
6. `attempt_count` is **not** incremented on claim (set once at job creation for a new attempt).
7. Pipeline execution runs only after `claim.may_execute` (`ACQUIRED` or idempotent `ALREADY_OWNED`).

## Consequences

- Two concurrent workers yield exactly one `ACQUIRED`.
- Conflicts are non-fatal for the losing worker (preparation halts without failing the job).
- Idempotent retry by the same `execution_id` does not reset `started_at` or bump attempts.
- Fencing tokens / lease stealing remain out of scope (Phase 3+).
- No `processing_job_id` column; aisle linkage remains `job.target_id` + active status checks.

## Alternatives considered

- Re-queue stale jobs to `QUEUED` — rejected; existing code and `JobStaleReconciler` already fail with `STALE_JOB`.
- In-memory locks for production — rejected; only used inside the memory adapter to emulate SQL atomicity in tests.
