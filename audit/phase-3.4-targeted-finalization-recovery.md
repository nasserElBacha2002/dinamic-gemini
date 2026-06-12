# Phase 3.4 — Targeted Manual Finalization Recovery

## 1. Executive summary

Phase 3.4 adds **explicit, manual, admin-only recovery operations** for incomplete v3 job finalization. Recovery uses authoritative Phase 3.3 evidence (`job_finalization_stages`, `job_artifact_manifest`, verifiers) and never re-executes the AI provider or `PersistAisleResultUseCase`.

**Non-goals honored:** no automatic scheduler, artifact outbox, background retry worker, provider re-execution, domain replacement, UI recovery controls.

## 2. Recovery architecture

```text
Admin API (POST /api/v3/admin/jobs/{job_id}/finalization/recover)
  → FinalizationRecoveryCoordinator
    → focused use case (verify | republish | terminalize | promote | reconcile | resume)
      → FinalizationRecoveryEligibility (assessment gate)
      → RecoverySession (lease + audit)
      → FinalizationStageRecorder + manifest stores (authoritative writes)
      → FinalizationAssessmentService (fresh assessment after each step)
```

## 3. Operations supported

| Operation | Use case |
| --------- | -------- |
| `verify` | `VerifyJobFinalizationUseCase` |
| `republish_artifacts` | `RepublishJobArtifactsUseCase` |
| `terminalize` | `TerminalizeRecoveredJobUseCase` |
| `promote` | `PromoteRecoveredOperationalResultUseCase` |
| `reconcile_aisle` | `ReconcileRecoveredAisleUseCase` |
| `reconcile_inventory` | `ReconcileRecoveredInventoryUseCase` |
| `resume` | `ResumeJobFinalizationUseCase` (coordinates the above) |

## 4. Eligibility matrix

| Assessment | Allowed recovery |
| ------------ | ---------------- |
| `COMPLETE` | None |
| `FAILED_BEFORE_DOMAIN_COMMIT` | Full new-job retry only |
| `DOMAIN_COMMITTED_ARTIFACTS_MISSING` | Republish artifacts |
| `ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING` | Terminalize |
| `TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING` | Promote / reconcile |
| `VERIFICATION_REQUIRED` | Verify first; republish/terminalize when preconditions met |
| `INCONSISTENT` | Manual investigation only (`verify` read-only reassessment allowed) |

## 5. Stage preconditions

| Operation | Requires |
| --------- | -------- |
| Republish artifacts | `DOMAIN_RESULTS=COMPLETED`, sources available |
| Terminalize | Domain complete, required artifacts verified |
| Promote | `JOB_TERMINALIZATION=COMPLETED`, job `SUCCEEDED` |
| Reconcile aisle | Job `SUCCEEDED`, acceptable promotion context |
| Reconcile inventory | `AISLE_RECONCILIATION=COMPLETED` |

## 6. Artifact source policy

`ArtifactRecoverySourceResolver` per kind:

| Kind | Exact local run dir | Reconstructed | Not reconstructable |
| ---- | ------------------- | ------------- | ------------------- |
| `execution_log` | Yes (if file exists) | No | Yes — domain rows cannot rebuild log |
| `hybrid_report_json` | Yes | From `result_json.report_path` only | If no file/report path |
| `hybrid_report_csv` | Optional | No | Optional; skipped unless present |

Statuses: `AVAILABLE_EXACT`, `AVAILABLE_RECONSTRUCTED`, `NOT_AVAILABLE`, `AMBIGUOUS`.

## 7. Idempotency guarantees

| Operation | Repeated execution |
| --------- | ------------------ |
| Republish | Skips verified artifacts; `ALREADY_COMPLETE` when all required verified |
| Terminalize | `ALREADY_COMPLETE` when job `SUCCEEDED` + terminalization stage complete |
| Promote | `ALREADY_OPERATIONAL` or `ALREADY_SUPERSEDED` |
| Reconcile aisle/inventory | `ALREADY_COMPLETE` when stage evidence complete |

Manifest identity remains `(job_id, artifact_kind)` with deterministic storage keys.

## 8. Concurrency / locking

`job_finalization_recovery_attempts` stores RUNNING attempts with `lease_expires_at`. A second concurrent recovery for the same job raises `RecoveryLeaseConflictError` → `CONCURRENCY_CONFLICT`.

Memory and SQL stores implement equivalent lease semantics.

## 9. Audit trail

Table `job_finalization_recovery_attempts` (migration `0039`):

- `recovery_id`, `job_id`, `operation`, `status`, timestamps
- `requested_by`, `source`
- `initial_assessment_outcome`, `final_assessment_outcome`
- sanitized `error_code` / `sanitized_error` (no stack traces or secrets)

Statuses: `RUNNING`, `SUCCEEDED`, `FAILED`, `PARTIAL`, `REJECTED`.

## 10. Authorization

`POST /api/v3/admin/jobs/{job_id}/finalization/recover` requires `get_current_admin` (Bearer JWT).

## 11. Cancellation policy

- Canceled before domain commit → not recoverable (`canceled_before_domain_commit`)
- Canceled after domain commit → verification/republish may proceed; terminalization requires `allow_canceled_terminalization=true`
- Never silently converts `CANCELED` → `SUCCEEDED`

## 12. Dry-run behavior

`dry_run=true` performs assessment + eligibility only; no lease, no repository writes, no stage/manifest mutations.

## 13. Failure / partial progress

Partial recovery preserves completed stage evidence. Recovery attempt recorded as `PARTIAL` or `FAILED`. Resume stops at first non-recoverable step and returns `PARTIALLY_RECOVERED`.

## 14. Tests

`backend/tests/infrastructure/pipeline/test_worker_phase3_part4_targeted_recovery.py` — dry-run, republish, idempotency, source unavailable, terminalize, stale promotion, inconsistent refusal, failed-before-domain, concurrent lease, audit sanitization.

## 15. SQL validation

SQL integration tests for recovery locking and audit persistence remain **pending** (ODBC unavailable in dev sandbox).

## 16. Deferred automation

- Automatic recovery scheduler
- Artifact outbox dispatcher
- Periodic retry worker
- Provider / pipeline re-execution
- UI recovery controls

## Recovery operation matrix

| Operation | Preconditions | Idempotency key | Mutations |
| --------- | ------------- | --------------- | --------- |
| Verify | Assessment not `COMPLETE` | job_id + verify | Optional stage verification timestamps |
| Republish artifacts | Domain complete + sources | (job_id, artifact_kind) | Manifest + optional REQUIRED_ARTIFACTS stage |
| Terminalize | Verified required artifacts | job_id terminalization stage | Job row + JOB_TERMINALIZATION stage |
| Promote | Job SUCCEEDED + terminalization | aisle operational CAS | OPERATIONAL_PROMOTION stage |
| Reconcile aisle | Terminalization complete | aisle processed state | AISLE_RECONCILIATION stage |
| Reconcile inventory | Aisle reconciliation complete | inventory derived status | INVENTORY_RECONCILIATION stage |
| Resume | Eligible assessment | per-step keys above | Sequential coordinated mutations |

## Validation commands

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall src
.venv/bin/python -c "from src.api.server import app; print('api_import_ok')"
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase3_part4_targeted_recovery.py
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase3_part3_durable_metadata.py
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase3_part2_finalization_semantics.py
```
