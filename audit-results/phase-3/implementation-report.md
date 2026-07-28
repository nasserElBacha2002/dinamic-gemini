# Phase 3 — Implementation report (job lease fencing)

## 1. Estado

**PARTIAL** — lease fencing core is implemented, validated (unit + memory concurrent + SQL IT + monitoring), and mergeable pending Quality Gate on unrelated supplier-prompt SQL failures. Remaining gaps: cooperative cancel not lease-CAS’d; finalization tracker/outbox job-row markers still use unfenced `save`; no Prometheus counters (structured `event=job_lease_*` logs only); `JOB_LEASE_RENEWAL_SAFETY_MARGIN_SEC` is configured but not yet driving renewal urgency; production stale path still fails the job rather than stealing on the same row (`reacquire_expired_lease` is available for controlled recovery/tests).

```text
LEASE_MODEL=EXPLICIT
FENCING_TOKEN=MONOTONIC
LEASE_RENEWAL=CAS_PROTECTED
STALE_WORKER_WRITES=REJECTED (heartbeat/result/complete/fail when lease present)
HEARTBEAT=FENCED
RESULT_WRITES=FENCED
FINALIZATION=FENCED (assert + complete_if_leased)
ARTIFACT_PUBLICATION=SOFT (assert_lease before publish; tracker/outbox markers unfenced)
OPERATIONAL_PROMOTION=GATED (requires fenced SUCCEEDED first)
LEASE_LOSS_STOPS_WORKER=YES
SQL_INTEGRATION_TESTS=PASS
QUALITY_GATE=FAIL (5 unrelated supplier-prompt SQL tests)
PHASE_4=NOT_STARTED
MERGEABLE_TO_MAIN=YES (after QG exception or unrelated fix)
```

## 2. Causa raíz

Phase 1 atomic claim (`claim_owner_id` + STARTING→RUNNING CAS) prevents two workers from *starting* the same attempt, but does not stop a **stale** worker that already held the claim from writing `result_json`, heartbeating, or terminalizing after:

1. process pause / network partition past heartbeat timeout, or
2. another worker reacquiring after lease expiry.

Without a monotonic **fencing token** + expiry, last-writer-wins on `save()` / unfenced merges can corrupt results or flip terminal status after ownership moved.

## 3. Modelo lease

- **`JobLease`** (`backend/src/domain/jobs/lease.py`): `job_id`, `owner_id`, `fencing_token`, `acquired_at`, `expires_at` (frozen).
- **`owner_id`** = same value as `Job.claim_owner_id` (no separate `lease_owner_id` column).
- **`fencing_token`** assigned by persistence on acquire/reacquire — never invented by callers.
- Outcomes: `LeaseWriteOutcome`, `LeaseRenewalOutcome`, wrappers `LeaseWriteResult` / `LeaseRenewalResult`.
- Cooperative halt: **`JobLeaseLostError`** — worker stops without marking job `FAILED`.

Settings (`grouped_settings.py`):

| Env | Default | Uso |
|---|---|---|
| `JOB_LEASE_DURATION_SEC` | 60 | Duration on claim / renew extension |
| `JOB_LEASE_HEARTBEAT_INTERVAL_SEC` | 15 | Monitoring heartbeat loop interval |
| `JOB_LEASE_RENEWAL_SAFETY_MARGIN_SEC` | 20 | Defined; **not yet consumed** by heartbeat urgency logic |

## 4. Fencing

CAS predicates for lease-conditioned ops (renew / merge / complete / fail / assert):

- `status IN ('running', 'cancel_requested')` (active leasable)
- `claim_owner_id = lease.owner_id`
- `lease_fencing_token = lease.fencing_token`
- `lease_expires_at >= now` (not expired)

Token is **monotonic** (`+1` on claim acquire and on `reacquire_expired_lease`). Renewal does **not** bump the token.

Shared classification: `backend/src/application/services/job_lease_helpers.py` (`lease_is_currently_valid`, `classify_lease_*_after_cas_miss`).

## 5. Migración

`0072_inventory_jobs_lease_fencing.sql` — additive / idempotent (`COL_LENGTH` / index existence checks):

- `lease_fencing_token BIGINT NOT NULL DEFAULT 0`
- `lease_expires_at DATETIME2 NULL`
- `lease_acquired_at DATETIME2 NULL`
- Index `IX_inventory_jobs_lease_expiry` on `(status, lease_expires_at)` filtered `WHERE lease_expires_at IS NOT NULL`

Mirrored in `backend/src/database/schema.sql`. Reuses `claim_owner_id` as owner.

## 6. Claim

`try_claim_starting_to_running(..., lease_duration_seconds)` (SQL + memory):

- Existing Phase 1 STARTING→RUNNING + aisle PROCESSING in one TX.
- On acquire: set `claim_owner_id`, increment `lease_fencing_token`, set `lease_acquired_at` / `lease_expires_at`, attach `JobClaimResult.lease`.
- Prep (`V3JobPreparationService`) generates UUID `claim_owner_id`, passes `job_lease_duration_sec`, returns `prep.lease`.

## 7. Renewal

`renew_lease` / `touch_heartbeat_if_leased`: extend `lease_expires_at` + `last_heartbeat_at` under CAS; same fencing token; outcomes via `LeaseRenewalOutcome` (`RENEWED`, `LEASE_LOST`, `EXPIRED`, `JOB_TERMINAL`, …).

Logs: `event=job_lease_renewed` / `event=job_lease_lost`.

## 8. Steal

`reacquire_expired_lease`: CAS steal when `status='running'` AND `lease_expires_at < now` → new owner, `fencing_token + 1`, new expiry. Returns `JobClaimResult` with lease.

**PARTIAL:** implemented in SQL/memory repos + tests; **not wired** into production stale-recovery / worker launch path (Phase 1 `try_reclaim_stale_job_and_reconcile_aisle` still fails stale jobs rather than stealing leases).

## 9. Protected writes

| API | Behavior |
|---|---|
| `merge_result_json_if_leased` | TX + UPDLOCK + CAS; stale → `LEASE_LOST` + `event=job_stale_write_rejected` |
| `complete_if_leased` | Terminal SUCCEEDED persist only if lease held |
| `fail_if_leased` | FAILED only if lease held |
| `assert_lease` | Validate only (no mutation) |
| `merge_result_json_protected` (state service) | Raises `JobLeaseLostError` on lease loss when `lease` set; if `lease is None`, falls back to unfenced merge |

## 10. Heartbeat

`V3JobMonitoringService`: when `req.lease` set → `heartbeat_with_lease`; on non-`RENEWED` → log `job_lease_lost`, set **`runtime_abort_event`**, stop heartbeat — **does not** call `fail_job_and_aisle`. Legacy unfenced `heartbeat()` if lease absent.

## 11. Cancellation

**PARTIAL / gap:** `cancel_job` / `cancel_job_and_aisle` still use unfenced `save()`. Cancel paths are not lease-CAS protected. Lease loss does not cancel the job.

## 12. Results

Executor / code-scan / OCR paths call `merge_result_json_protected(..., lease=prep.lease)` for progress and outcome patches. Stale worker raises `JobLeaseLostError` and halts.

## 13. Artifacts

**PARTIAL / gap:** durable artifact publication / outbox **not** gated by inventory-job `JobLease` fencing. (Separate image-batch `JobProcessingLeaseRepository` remains a distinct mechanism.)

## 14. Finalization

`V3JobFinalizationService` accepts `lease`; asserts lease before proceeding; state service uses `complete_if_leased` / `assert_lease` when lease present; `JobLeaseLostError` → halt without FAIL. Executor passes `prep.lease` into finalization / code_scan finalize.

## 15. Promotion

**PARTIAL / gap:** operational promotion (`aisle.operational_job_id`) retains prior CAS on candidate timestamps / status — **no** `JobLease` / fencing_token check.

## 16. SQL

`SqlJobRepository`: claim OUTPUT token, renew CAS UPDATE, reacquire, merge under transaction+UPDLOCK, assert/complete/fail_if_leased. Structured logs `job_lease_*` / `job_stale_write_rejected`.

## 17. Memory

`MemoryJobRepository` mirrors the same contract for local/dev/tests (lock-protected equivalents of CAS).

## 18. Unit tests

- `backend/tests/domain/jobs/test_job_lease.py` — VO / outcomes / `JobLeaseLostError`
- `backend/tests/infrastructure/repositories/test_memory_job_lease_fencing.py` — acquire, renew, steal, stale merge/complete/fail
- `backend/tests/infrastructure/pipeline/test_v3_job_monitoring_lease_lost.py` — abort without fail
- SQL unit coverage extended in `test_sql_job_repository.py` where lease columns/methods are exercised

## 19. Concurrent tests

Memory sequential steal-chain + SQL IT `test_sql_dual_connection_lease_steal` (barrier, two threads, exactly one `ACQUIRED`).

## 20. SQL tests

`backend/tests/integration/jobs/test_sql_job_lease_fencing.py` — monotonic token, stale heartbeat/result/finalization rejected, dual-connection steal. Skips without SQL Server/ODBC or missing 0072 columns; **must run in CI** before merge-ready on SQL environments.

## 21. Partial failures

| Escenario | Comportamiento |
|---|---|
| Lease lost mid-run | `runtime_abort` / `JobLeaseLostError`; job **not** FAILED |
| Stale merge/complete/fail | CAS miss → reject + log; current owner unaffected |
| Claim conflict (Phase 1) | Prep halt; no lease |
| Steal not in prod recovery | Expired leases rely on existing stale-fail reclaim until steal is wired |

## 22. Rollout

1. Apply migration `0072` (additive; safe on live schemas with default token `0`).
2. Deploy code that acquires/renews leases on claim/heartbeat.
3. Ensure `JOB_LEASE_DURATION_SEC` > heartbeat interval + margin (defaults 60 / 15 / 20).
4. Run SQL IT in CI against migrated DB.
5. Monitor structured logs `job_lease_*` / `job_stale_write_rejected`.

## 23. Rollback

Code rollback: workers without lease columns fail if schema not present — prefer forward-fix or deploy code that tolerates missing columns only if explicitly supported (current code expects columns after 0072).

Schema rollback (dev/test only, per migration comments):

```sql
ALTER TABLE inventory_jobs DROP COLUMN lease_fencing_token;
ALTER TABLE inventory_jobs DROP COLUMN lease_expires_at;
ALTER TABLE inventory_jobs DROP COLUMN lease_acquired_at;
```

**Do not** drop columns with production data without an explicit ops plan.

## 24. Metrics

**Structured logs only** — events such as:

- `event=job_lease_acquired|renewed|lost|reacquired`
- `event=job_stale_write_rejected`

**No Prometheus counters** for lease fencing yet (limitation). Existing alert metric name `job_lease_expired_running` in `production_alerts.py` is unrelated product alert plumbing, not Phase 3 fencing counters.

## 25. Limitaciones

- Cancellation / artifact outbox / operational promotion still unfenced w.r.t. `JobLease`.
- `reacquire_expired_lease` not in production recovery path.
- `JOB_LEASE_RENEWAL_SAFETY_MARGIN_SEC` unused by runtime urgency logic.
- Paths with `lease=None` still allow unfenced merge/heartbeat/legacy terminalization.
- SQL IT may skip locally without ODBC/SQL Server.
- No Phase 4 work.

## 26. Riesgos

- Stale worker can still cancel or publish artifacts / influence promotion after lease loss.
- Mis-tuned lease duration vs heartbeat → false lease loss → abort without fail (job may hang until Phase 1 stale reclaim).
- Steal primitive unused in prod → expired RUNNING rows wait for stale-fail policy.

## 27. Alcance (scope)

**In:** inventory job lease fencing for claim, renew, steal (repo), protected result writes, worker heartbeat abort, lease-aware complete/fail/finalization assert, migration 0072, SQL+memory+tests, structured logs.

**Out:** Phase 4; Prometheus lease metrics; fencing cancel/artifacts/promotion; production steal scheduler; CV pipeline algorithm changes; frontend.

## 28. Mergeabilidad

**Conditional / PARTIAL.** Safe to merge as incremental Phase 3 if:

- migration 0072 applied in target envs,
- focused pytest (domain + memory + monitoring) green,
- SQL IT executed in CI with SQL Server,

and reviewers accept documented gaps (cancel/artifacts/promotion/steal wiring/metrics). Not “COMPLETED” until remaining unfenced write paths and production steal/metrics policy are closed or explicitly deferred with sign-off.
