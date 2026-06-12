# Phase 3.3 — Durable Finalization Metadata

## 1. Executive summary

Phase 3.3 introduces **authoritative stage evidence** (`job_finalization_stages`, `job_artifact_manifest`) separate from the denormalized `inventory_jobs` finalization summary fields introduced in Phase 3.2. Domain persistence evidence is written **transactionally** inside the job-result UoW when using memory or SQL backends. A read-only **assessment service** normalizes evidence for recovery planning without executing recovery. Job detail API exposes sanitized stage assessments.

**Non-goals honored:** no recovery commands, artifact outbox, automatic retries, background reconciliation, or UI recovery controls.

## 2. Authoritative metadata source

| Layer | Role |
| ----- | ---- |
| `job_finalization_stages` | **Authoritative** per-stage status, evidence level, timestamps, errors, version |
| `job_artifact_manifest` | **Authoritative** per-artifact publication evidence |
| `inventory_jobs.finalization_*` | **Projection/cache** refreshed from stage store after authoritative writes |

Projection failures are logged (`finalization_summary_projection_failed`) and do **not** downgrade authoritative stage rows.

## 3. Stage model

Stages (ordered): `DOMAIN_RESULTS`, `REQUIRED_ARTIFACTS`, `JOB_TERMINALIZATION`, `OPERATIONAL_PROMOTION`, `AISLE_RECONCILIATION`, `INVENTORY_RECONCILIATION`.

Statuses: `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELED`, `VERIFICATION_REQUIRED`, `UNKNOWN`.

Domain types: `backend/src/domain/jobs/finalization_evidence.py`.

## 4. Evidence levels

| Level | Semantics |
| ----- | --------- |
| `TRANSACTIONAL` | Marker commits in same DB transaction as the operation |
| `CONFIRMED` | Separate commit after operation; marker present = strong evidence |
| `POSITIVE_EVIDENCE_ONLY` | Post-operation marker; absence does not prove rollback |
| `DERIVED` | Inferred from other durable data (read-only verifiers) |
| `VERIFICATION_REQUIRED` | Manual or automated verification needed |
| `UNKNOWN` | Historical / insufficient evidence |

## 5. Legal transitions

Implemented in `finalization_stage_transitions.py`. Notable additions for Phase 3.3:

- `NOT_STARTED → COMPLETED` (transactional UoW first write)
- `COMPLETED → VERIFICATION_REQUIRED` (reconcile job row vs missing stage)
- Optimistic concurrency raises `FinalizationStageConcurrencyError` **before** transition validation when `expected_version` mismatches.

Invalid examples rejected: `COMPLETED → IN_PROGRESS`, `COMPLETED → NOT_STARTED`, `FAILED → COMPLETED` without verification path.

## 6. Transaction map

```text
[UoW TX] delete scope → insert domain → recompute → DOMAIN_RESULTS=COMPLETED (TRANSACTIONAL) → commit
[separate] durable artifact upload → manifest rows → REQUIRED_ARTIFACTS stage
[separate] job terminalization save → JOB_TERMINALIZATION stage
[separate] operational promotion → OPERATIONAL_PROMOTION stage
[separate] aisle update → AISLE_RECONCILIATION stage
[separate] inventory reconcile → INVENTORY_RECONCILIATION stage
[after each stage write] projection refresh → inventory_jobs summary fields
```

## 7. Domain persistence evidence guarantees

- Memory UoW: `MemoryFinalizationEvidenceWriter` buffers stage write; flushed on `commit()`, discarded on `rollback()`.
- SQL UoW: `SqlFinalizationEvidenceWriter` writes into `job_finalization_stages` using the open transaction connection.
- Post-UoW tracker marker (`record_domain_persisted`) skips downgrading when `TRANSACTIONAL` evidence already exists.

**Crash window:** failure between UoW commit and summary projection leaves authoritative `TRANSACTIONAL` stage row while `inventory_jobs` summary may be stale — assessment reads authoritative evidence.

## 8. Artifact manifest design

Table `job_artifact_manifest` with deterministic `(job_id, artifact_kind)` identity.

Required kinds: `execution_log`, `hybrid_report_json`. Optional: `hybrid_report_csv`.

Statuses: `PENDING`, `PUBLISHED`, `FAILED`, `UNKNOWN`.

## 9. Verification rules

| Verifier | Purpose |
| -------- | ------- |
| `JobDomainResultVerifier` | Complete job-scoped snapshot (positions/products/evidence consistency; empty valid vs missing) |
| `JobArtifactVerifier` | Manifest + storage existence/size (read-only; no re-upload) |
| `FinalizationAssessmentService` | Normalized outcome + recovery_candidate flag (read-only) |
| `assert_operational_pointer_invariant` | `operational_job_id` → referenced job `SUCCEEDED` |

## 10. Crash windows

| Window | Authoritative evidence | Summary may be stale |
| ------ | ---------------------- | -------------------- |
| UoW commit → tracker marker | TRANSACTIONAL domain stage | yes |
| Artifact upload → manifest/stage write | manifest rows | yes |
| Stage write → projection refresh | stage row | yes |

## 11. Projection behavior

`FinalizationProjectionService.refresh_summary()` maps stage rows → `finalization_status`, `current_finalization_step`, `last_completed_finalization_step`, `domain_persisted_at`, `artifacts_published_at`. Save failures are logged only.

## 12. Historical job behavior

Jobs without stage rows: stages assessed as `UNKNOWN` / `evidence_level=UNKNOWN`. A historical `SUCCEEDED` job does **not** infer artifact or reconciliation completion.

## 13. API visibility

`GET .../jobs/{job_id}` (`JobDetailResponse`) includes optional `finalization_assessment` block with stage statuses, evidence levels, verification flags. Raw exceptions, stack traces, and storage secrets are not exposed.

## 14. Concurrency safeguards

Stage rows include `version`. Updates use `expected_version` compare-and-set; conflicts raise `FinalizationStageConcurrencyError`.

## 15. Tests

`backend/tests/infrastructure/pipeline/test_worker_phase3_part3_durable_metadata.py` — T1–T15 covering transactional domain evidence, crash window, empty snapshot, incomplete scope, manifest, partial publication, storage verification, terminalization gap, operational invariant, reconciliation separation, concurrency, illegal transitions, historical unknowns, API sanitization, projection failure.

## 16. Deferred recovery work

- Recovery commands / admin repair endpoints
- Artifact outbox and retry worker
- Automatic reconciliation retries
- Historical backfill inventing stage completion
- UI recovery controls

## Durability matrix

| Stage | Authoritative source | Evidence level | Transactional with operation | Verification method |
| ----- | -------------------- | -------------- | ---------------------------- | ------------------- |
| Domain results | `job_finalization_stages` | TRANSACTIONAL (UoW) / POSITIVE_EVIDENCE_ONLY (post marker) | Yes (UoW) | `JobDomainResultVerifier` |
| Required artifacts | `job_artifact_manifest` + stage row | CONFIRMED | No | `JobArtifactVerifier` |
| Job terminalization | stage row + `inventory_jobs.status` | CONFIRMED / VERIFICATION_REQUIRED | No | job row + stage cross-check |
| Operational promotion | stage row | CONFIRMED | No | promotion repo / aisle pointer |
| Aisle reconciliation | stage row | CONFIRMED | No | aisle processing status |
| Inventory reconciliation | stage row | CONFIRMED | No | inventory derived status |

## Assessment scenarios

| Scenario | Assessment result | Recovery candidate | Automatic action in 3.3 |
| -------- | ----------------- | -----------------: | ----------------------- |
| Domain commit, summary marker missing | `VERIFICATION_REQUIRED` or `DOMAIN_COMMITTED_ARTIFACTS_MISSING` | yes | None |
| Required artifact missing | `DOMAIN_COMMITTED_ARTIFACTS_MISSING` | yes | None |
| Job succeeded, promotion missing | `TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING` | yes | None |
| Inventory reconciliation failed | `TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING` | yes | None |
| Historical job with unknown evidence | `VERIFICATION_REQUIRED` / not `COMPLETE` | yes | None |
