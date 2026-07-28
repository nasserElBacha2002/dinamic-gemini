# ADR — Atomic job claiming and stale aisle reconciliation

## Status

Accepted (Phase 1 corrections — 2026-07-28)

## Context

Technical audit v2 identified two P0 issues:

1. **Double job execution** — `V3JobExecutionStateService.mark_running` used get/mutate/save without a compare-and-set predicate on `status`.
2. **Stale reclaim inconsistency** — bulk reclaim failed jobs without reconciling the related aisle.

The first Phase 1 implementation used `Job.execution_id` as the ownership token. That is incorrect for on-demand workers: multiple processes on the same job row share the same `execution_id`, so a CAS loser could receive `ALREADY_OWNED` and `may_execute=True`.

## Decision

1. Introduce explicit claim outcomes (`JobClaimOutcome`) and `JobClaimResult`.
2. Separate identities:
   - `execution_id` = persisted attempt identifier (unchanged semantics)
   - `claim_owner_id` = unique worker-invocation token (new column, migration `0071`)
3. Implement `JobRepository.try_claim_starting_to_running` with SQL CAS `WHERE status = 'starting'` setting `claim_owner_id`, plus aisle `PROCESSING` in the **same transaction**.
4. `ALREADY_OWNED` only when both caller and persisted `claim_owner_id` are non-null and equal. Null tokens never grant ownership. Matching `execution_id` alone never grants ownership.
5. `may_execute` is true only for `ACQUIRED` or same-owner `ALREADY_OWNED`.
6. Stale policy remains **Option C**: active stale jobs → `FAILED` / `STALE_JOB`, then reconcile aisle only if no other active job targets the same aisle — inside **`try_reclaim_stale_job_and_reconcile_aisle`** (single SQL transaction).
7. Shared field transition via `apply_stale_failure_fields` (memory) / equivalent SQL SET list.
8. No RMW fallbacks, no permissive `getattr(..., True)`, claim/reclaim are `@abstractmethod` on the port.
9. `attempt_count` is **not** incremented on claim.

## Consequences

- Two concurrent workers with different `claim_owner_id` yield exactly one `ACQUIRED` and one `CONFLICT`.
- Conflicts are non-fatal for the losing worker (preparation halts without failing the job).
- Idempotent retry by the same `claim_owner_id` does not reset `started_at` or bump attempts.
- Requires additive migration `0071_inventory_jobs_claim_owner_id.sql`.
- Fencing tokens / lease stealing remain out of scope (Phase 3+).

## Alternatives considered

- Keep ownership = `execution_id` — rejected; same-row workers share it.
- Drop `ALREADY_OWNED` and allow only `ACQUIRED` to execute — viable, but same-owner idempotent retry is useful; kept with strict claim-owner equality.
- Re-queue stale jobs to `QUEUED` — rejected; existing code fails with `STALE_JOB`.
- In-memory locks for production — rejected; only used inside the memory adapter.
