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
| Missing job with orphan evidence | `INCONSISTENT` (`orphan_finalization_evidence`) | no | None |
| Stage order gap (later complete, earlier missing) | `INCONSISTENT` (`stage_order_gap`) | no | None |
| Published manifest, storage missing | `DOMAIN_COMMITTED_ARTIFACTS_MISSING` | yes | None |
| Published manifest, size mismatch | `INCONSISTENT` (`artifact_storage_mismatch`) | no | None |
| Storage verification unavailable | `VERIFICATION_REQUIRED` | yes | None |
| All stages complete + verified artifacts + valid domain | `COMPLETE` | no | None |

## 17. Review corrections (post code review)

### Central artifact policy

`backend/src/domain/jobs/artifact_policy.py` is the single source of truth:

- `REQUIRED_ARTIFACT_KINDS`: `execution_log`, `hybrid_report_json`
- `OPTIONAL_ARTIFACT_KINDS`: `hybrid_report_csv`
- `ALL_EXPECTED_ARTIFACT_KINDS`: union of required + optional

Publisher, manifest recorder, verifier, assessment, and tests import from this module — no duplicated kind lists.

### Manifest pre-registration

`ensure_expected_entries()` creates deterministic `PENDING` rows for all expected kinds before publication. Required artifacts never disappear from the manifest; absent uploads are explicitly `FAILED` with a sanitized reason.

### Required-set completeness

`required_kinds_published()` validates the full required set (not partial overlap). `missing_required_kinds()` supports diagnostics.

### Storage verification integration

`JobArtifactVerifier.verify_required()` checks every required kind even when no manifest row exists. `FinalizationAssessmentService` actively uses verifier results:

| Condition | Assessment |
| --------- | ---------- |
| All required artifacts `CONFIRMED` | Continue assessment |
| Required manifest absent / pending / failed | `DOMAIN_COMMITTED_ARTIFACTS_MISSING` |
| Storage object missing | `DOMAIN_COMMITTED_ARTIFACTS_MISSING` |
| Size/hash mismatch | `INCONSISTENT` |
| Storage cannot be checked | `VERIFICATION_REQUIRED` |
| Published but no storage key | `INCONSISTENT` |

### Evidence levels (corrected)

| Event | Evidence level |
| ----- | -------------- |
| Stage marked `IN_PROGRESS` | `POSITIVE_EVIDENCE_ONLY` |
| Artifact uploaded, manifest saved, not externally verified | `POSITIVE_EVIDENCE_ONLY` |
| Storage existence + metadata verified | `CONFIRMED` |
| UoW + stage update in same transaction | `TRANSACTIONAL` |
| Verification unavailable | `VERIFICATION_REQUIRED` |
| Derived from durable metadata only | `DERIVED` |

### Domain snapshot verification

Removed global `positions == products == evidence` assumption. Verifier checks referential integrity per entity (products/evidence/labels reference valid position IDs; each position requires ≥1 product). Multiple evidences per position is valid.

Empty snapshot is `CONFIRMED_EMPTY_VALID` only when `DOMAIN_RESULTS=COMPLETED` with `TRANSACTIONAL` evidence (via injected `stage_store`). Without transactional stage evidence, zero rows → `NOT_FOUND`, `AMBIGUOUS`, or `VERIFICATION_REQUIRED`.

### Strict COMPLETE invariant

`COMPLETE` requires all stages `COMPLETED` with timestamps, `job.status=SUCCEEDED`, required artifacts verified (`CONFIRMED`), operational pointer valid, and domain snapshot complete. Stage order gaps → `INCONSISTENT`.

### Missing-job assessment

Missing job → `INCONSISTENT`, `recovery_candidate=false`, `blocking_reason=job_not_found` or `orphan_finalization_evidence`. Never classified as `FAILED_BEFORE_DOMAIN_COMMIT`.

### Optimistic concurrency

Create: `expected_version=None`, row must not exist. Update: `expected_version=current version`, row must match. Blind overwrites raise `FinalizationStageConcurrencyError` / `ArtifactManifestConcurrencyError`. UoW evidence writers pass current version when flushing buffered stage writes.

### Projection determinism

`refresh_summary()` fully derives `domain_persisted_at`, `artifacts_published_at`, `finalization_completed_at`, and error fields from authoritative evidence every refresh — stale timestamps are cleared when evidence is no longer valid. Projection failures log structured fields (`job_id`, `authoritative_last_stage`, `projection_target_status`, `exception_type`) without downgrading authoritative evidence.

### Migration 0038

Foreign keys omitted to preserve compatibility with existing cleanup/retention policies. Check constraints deferred to a forward-only migration if needed after data validation.

### SQL integration validation

SQL Server integration tests for migration, manifest CAS, and transactional domain rollback remain **pending** (ODBC driver unavailable in CI/dev sandbox).

### Review corrections matrix

| Finding | Correction | Test |
| ------- | ---------- | ---- |
| Missing import | Restored `AisleJobLaunchService`, `ActiveJobExistsError`; API entrypoint `src.api.server` | `test_p3_3_corr_t01_api_import_smoke` |
| Required artifact absent | Central policy + `required_kinds_published` exact-set validation | `test_p3_3_corr_t02_one_required_artifact_missing` |
| Storage verification ignored | `verify_required()` integrated in assessment | `test_p3_3_t07`, corr T4–T6 |
| Invalid domain cardinality | Referential verifier replaces count equality | `test_p3_3_t04`, corr T7–T8 |
| Loose COMPLETE rule | Strict all-stages + verified artifacts | `test_p3_3_corr_t11`, corr T17 |
| Missing-job assessment | `INCONSISTENT` with `orphan_finalization_evidence` | `test_p3_3_corr_t12` |
| Weak CAS behavior | Strict create/update version contract | `test_p3_3_t11`, `test_p3_3_corr_t13` |
| Stale projection timestamps | Deterministic refresh clears invalid timestamps | `test_p3_3_corr_t16` |
| Manifest PENDING lost | `upsert_entry` preserves all statuses literally | corr T15 (memory/SQL) |
| Validation commands | `compileall`, API import, pytest suites | See validation summary |

### Validation commands

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall src
.venv/bin/python -c "from src.api.server import app; print('api_import_ok')"
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase3_part3_durable_metadata.py
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase3_part2_finalization_semantics.py
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase2_part2_transactional_idempotency.py
.venv/bin/pytest tests/infrastructure/pipeline/test_worker_phase2_part3_operational_promotion_concurrency.py
.venv/bin/pytest tests/infrastructure/pipeline/test_v3_job_executor_coordination.py
```
