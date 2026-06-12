# Phase 3.2 — Robust Finalization Semantics (Implementation)

## 1. Summary of changes

Phase 3.2 introduces an explicit, durable finalization state model on `inventory_jobs`, a specific error taxonomy for post-pipeline failures, stepwise progress recording around finalization, and corrected cancellation routing during artifact publication.

**In scope (implemented):**

- Durable finalization metadata columns + domain enums
- `JobFinalizationTracker` for progress updates
- `V3JobExecutor` finalization flow with ordered exception handling
- `V3JobExecutionStateService.finalize_success()` with per-step failure classification
- Artifact error types (`ArtifactStoreUnavailableError`, `ArtifactPublishError`, `ArtifactPublishPartialError`)
- Backward-compatible optional API fields on `JobSummary`
- Focused test suite (`test_worker_phase3_part2_finalization_semantics.py`) + updates to existing worker tests

**Explicitly not implemented (deferred to Phase 3.3+):**

- `recover_job_finalization` command
- Artifact outbox / automatic artifact retries
- Background retry worker
- Large `V3JobExecutor` decomposition
- UI recovery controls
- Provider failover changes

## 2. Finalization state model

Two concepts are modeled separately (never conflated):

| Concept | Field | Enum |
| ------- | ----- | ---- |
| Overall finalization lifecycle | `finalization_status` | `NOT_STARTED`, `IN_PROGRESS`, `FAILED`, `COMPLETED`, `CANCELED` |
| Step currently executing | `current_finalization_step` | `PERSIST_DOMAIN_RESULTS`, `PUBLISH_ARTIFACTS`, `TERMINALIZE_JOB`, `PROMOTE_OPERATIONAL_RESULT`, `UPDATE_AISLE`, `RECONCILE_INVENTORY` |
| Last step completed successfully | `last_completed_finalization_step` | `NONE`, `DOMAIN_RESULTS_PERSISTED`, `ARTIFACTS_PUBLISHED`, `JOB_TERMINALIZED`, `OPERATIONAL_RESULT_PROMOTED`, `AISLE_UPDATED`, `INVENTORY_RECONCILED` |

Additional durable fields:

- `finalization_error_code`, `finalization_error_metadata`
- `finalization_started_at`, `finalization_completed_at`
- `domain_persisted_at`, `artifacts_published_at`

Domain definitions: `backend/src/domain/jobs/finalization.py`  
Tracker implementation: `backend/src/infrastructure/pipeline/job_finalization_tracker.py`

## 3. Error taxonomy

Finalization failures use specific codes (replacing generic `PROCESSING_FAILED` where the failure is finalization-scoped):

| Code | When used |
| ---- | --------- |
| `DOMAIN_PERSISTENCE_FAILED` | Persist UoW failure (includes recompute failure inside the same transaction) |
| `ARTIFACT_STORE_UNAVAILABLE` | Artifact store not configured / unavailable before upload |
| `ARTIFACT_PUBLISH_FAILED` | Required artifact upload failure (no prior successful required uploads in attempt) |
| `ARTIFACT_PUBLISH_PARTIAL` | At least one required artifact uploaded, then a later required artifact failed |
| `JOB_TERMINALIZATION_FAILED` | Job row terminal save failed after artifacts |
| `OPERATIONAL_PROMOTION_FAILED` | Operational promotion rejected or raised |
| `AISLE_RECONCILIATION_FAILED` | Aisle `PROCESSED` save failed |
| `INVENTORY_RECONCILIATION_FAILED` | Inventory status reconcile failed |
| `FINALIZATION_CANCELED` | Effective cancellation during finalization |

Provider/pipeline failures before finalization still use `PROCESSING_FAILED` via `fail_job_and_aisle`.

Recompute failures are **not** exposed as `RECOMPUTE_FAILED`; they roll back the persist UoW and are classified as `DOMAIN_PERSISTENCE_FAILED` with exception metadata.

## 4. Cancellation policy

### Before domain commit

- Job → `CANCELED`
- `finalization_status` → `CANCELED` (if finalization had begun)
- `last_completed_finalization_step` → `NONE`
- No committed domain rows from this attempt
- Error code → `FINALIZATION_CANCELED` (not artifact failure codes)

### After domain commit (post-UoW)

When cancellation is detected at artifact checkpoints after persistence:

- Job → `CANCELED`
- `finalization_status` → `CANCELED`
- `last_completed_finalization_step` → `DOMAIN_RESULTS_PERSISTED`
- Domain rows **remain** job-scoped and non-operational
- Artifacts are **not** published
- `finalization_error_metadata.cancel_after_domain_commit = true`
- No cleanup of committed results

### Exception ordering (artifact block)

```python
except PipelineCancellationRequestedError:
    raise
except ArtifactPublishPartialError:
    ...
except (ArtifactPublishError, FileNotFoundError):
    ...
except Exception:
    ...
```

Cancellation at `pre_upload` is no longer swallowed as a generic artifact failure.

## 5. Transactional guarantees

**Unchanged from Phase 2:**

- Delete-replace, result inserts, and job-scoped recompute run in one `JobResultUnitOfWork` transaction.
- Recompute failure rolls back the entire persistence transaction.

**Phase 3.2 addition:**

- `DOMAIN_RESULTS_PERSISTED` is written **immediately after** UoW commit via `JobFinalizationTracker.record_domain_persisted()` (acceptable fallback — see below).

## 6. Known crash windows

| Window | Risk | Mitigation in Phase 3.2 |
| ------ | ---- | ------------------------ |
| Between UoW commit and `record_domain_persisted()` | Rows committed but marker absent | Documented in tracker; recovery must verify rows by `job_id` |
| After UoW commit, before artifact upload | Committed rows, no artifacts | Classified on next failure or cancel |
| After artifact upload, during terminalization | Artifacts durable, job not SUCCEEDED | `last_completed=ARTIFACTS_PUBLISHED`, specific terminal error |
| `mark_success` / terminal saves | Multiple independent saves | Each step records progress; split state is explicit in metadata |

## 7. Success invariants

Success is **not** defined circularly via `finalization_status=COMPLETED` alone.

**Preconditions before terminalization (`finalize_success`):**

- Domain results committed (UoW committed + `DOMAIN_RESULTS_PERSISTED` marker)
- Required worker durable artifacts published
- No effective pre-terminal cancellation
- Job in executable non-terminal state

**Terminal sequence (`finalize_success`):**

1. Terminalize job row (`SUCCEEDED`, `result_json` with artifacts)
2. Promote operational result (production mode)
3. Mark aisle `PROCESSED`
4. Reconcile inventory
5. `tracker.complete()` → `finalization_status=COMPLETED`, `last_completed=INVENTORY_RECONCILED`

**Final outcome on full success:**

- `job.status = SUCCEEDED`
- `finalization_status = COMPLETED`
- `last_completed_finalization_step = INVENTORY_RECONCILED`

Inventory reconciliation **is** part of the success path in current product semantics; failure leaves job `FAILED` with `INVENTORY_RECONCILIATION_FAILED` while preserving earlier step markers.

## 8. Artifact criticality assumptions

- Worker durable artifacts (`execution_log`, `hybrid_report`, etc.) published via `WorkerDurableArtifactPublisher` are **required** for success.
- Optional artifacts that fail without any prior successful required upload → `ARTIFACT_PUBLISH_FAILED`.
- Some required artifacts succeed, then a later required artifact fails → `ARTIFACT_PUBLISH_PARTIAL`; published references are preserved in metadata (`published_artifact_kinds` / partial error metadata).
- Optional-only failures without blocking required uploads: behavior unchanged from pre-3.2 (not separately classified in this phase).

## 9. Backward compatibility

- Migration `0037_inventory_jobs_finalization_metadata.sql` adds columns with safe defaults (`not_started`, `none`).
- Historical jobs remain readable; unset fields default at entity/ORM layer.
- `JobSummary` exposes new fields as optional — existing API consumers unaffected.
- Job status filters and retry creation unchanged.
- `mark_success()` remains as backward-compatible wrapper delegating to `finalize_success()` when a tracker is supplied.

## 10. Tests added

| Test | File | Coverage |
| ---- | ---- | -------- |
| T01 persistence rollback | `test_worker_phase3_part2_finalization_semantics.py` | Domain failure metadata, no rows |
| T02 recompute in UoW | same | `DOMAIN_PERSISTENCE_FAILED` |
| T03 artifact after commit | same | `ARTIFACT_PUBLISH_FAILED`, domain rows kept |
| T04 partial artifacts | same | `ARTIFACT_PUBLISH_PARTIAL` |
| T05 cancel before persist | same | `CANCELED`, no rows |
| T06 cancel at pre_upload | same | Post-commit cancel policy |
| T07 terminalization failure | same | `JOB_TERMINALIZATION_FAILED` |
| T07b promotion hard fail | same | `OPERATIONAL_PROMOTION_FAILED` |
| T08 aisle failure | same | `AISLE_RECONCILIATION_FAILED` |
| T09 inventory failure | same | `INVENTORY_RECONCILIATION_FAILED` |
| T10 happy path | same | Full progression + timestamps |
| T11 historical compatibility | same | Entity defaults |
| T12 cancel not swallowed | same | Exception ordering regression |

Updated: `test_worker_operational_safety_phase1.py`, `test_v3_job_executor_coordination.py`, `test_worker_phase2_part1_idempotency_characterization.py`.

## 11. Deferred work (Phase 3.3+)

- Targeted recovery command (`recover_job_finalization`)
- Artifact-only retry / outbox pattern
- Recompute-only recovery path
- Automatic backoff retry worker
- UI surfaces for partial finalization recovery
- Executor decomposition
- SQL integration validation for finalization columns under concurrency

## Appendix: Is `DOMAIN_RESULTS_PERSISTED` transactional?

**No — post-UoW marker (acceptable fallback).**

It is written in a separate `job_repo.save()` immediately after `PersistAisleResultUseCase.execute()` returns (UoW already committed). A crash between commit and marker leaves committed rows without the marker. Recovery logic must verify persisted rows by `job_id`; marker absence is not proof of rollback. This limitation is documented in `JobFinalizationTracker` class docstring.
