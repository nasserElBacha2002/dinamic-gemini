# Phase 3 — Implementation report (job lease fencing) — corrections

## 1. Estado

**CORRECTIONS applied** — fencing gaps from the Phase 3 code review are closed for merge readiness of the lease model. Phase 4 was not started.

```text
LEASE_MODEL=EXPLICIT
FENCING_TOKEN=MONOTONIC
LEASE_RENEWAL=CAS_PROTECTED + SAFETY_MARGIN
STALE_WORKER_WRITES=REJECTED
DOMAIN_PERSIST=SAME_TX_FENCE (UPDLOCK) + post-UoW leased marker
FINALIZATION_TRACKER=LEASE_CAS (no save on active jobs)
ARTIFACT_PUBLICATION=TOKEN_SCOPED_KEYS + lease gate before mark_published
CANCEL_ACK=LEASE_CAS (external request remains unfenced)
OPERATIONAL_PROMOTION=REQUIRES SUCCEEDED + fencing_token>=1
GLOBAL_FALLBACK=LEASE_REQUIRED
NULL_EXPIRY=INVALID (lease_not_initialized)
PORTS=ABSTRACT lease ops
RECOVERY_POLICY=STALE_FAIL (reacquire = test/admin)
METRICS=LOW_CARDINALITY counters
QUALITY_GATE=supplier-prompt id length fixed
PHASE_4=NOT_STARTED
```

## 2. Causa raíz (corrections)

Initial Phase 3 fencing was **partial**: domain persist / tracker / artifacts / cancel ack / global fallback / null expiry still allowed stale side effects. TOCTOU on assert-then-write was closed with same-TX UPDLOCK for domain persist and CAS writes for metadata/artifacts/cancel.

## 3. Side effects protegidos

| Área | Protección |
|---|---|
| Domain persist | `SqlJobResultUnitOfWork.fence_job_lease` (UPDLOCK) + leased post-UoW marker |
| Finalization tracker | `update_finalization_if_leased` (incl. SUCCEEDED for post-terminal steps) |
| Artifacts | token-scoped keys `jobs/{id}/ft{token}/…` + assert before mark published |
| Global fallback | `merge_result_json_protected(..., lease=required)` |
| Cancel ack | `acknowledge_cancel_if_leased` |
| Promotion | re-read job; require SUCCEEDED + `lease_fencing_token >= 1` |
| Heartbeat | renew + safety margin abort |

## 4. Recovery

Production remains **stale-fail** (expire → fail job → new attempt). `reacquire_expired_lease` is test/admin only (documented on the port).

## 5. Rollback 0072 (dev/test only)

```sql
DROP INDEX IX_inventory_jobs_lease_expiry ON inventory_jobs;
ALTER TABLE inventory_jobs DROP CONSTRAINT DF_inventory_jobs_lease_fencing_token;
ALTER TABLE inventory_jobs DROP COLUMN lease_fencing_token, lease_expires_at, lease_acquired_at;
```

## 6. Limitaciones reales

- Domain rows remain job-scoped (no separate staging tables); visibility is via operational promotion.
- Memory repos return live object references; `_terminalize_job_row` deep-copies before SUCCEEDED mutation.
- Artifact background reclaim paths without a tracker lease gate remain soft (worker inline path is fenced).

## 7. Mergeabilidad

Lease correction suites green (including SQL IT). Supplier-prompt VARCHAR(36) test IDs shortened. Phase 4 not started.
