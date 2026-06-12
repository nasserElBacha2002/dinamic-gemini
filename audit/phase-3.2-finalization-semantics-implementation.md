# Phase 3.2 — Robust Finalization Semantics (Implementation)

## 1. Summary of changes

Phase 3.2 introduces an explicit, durable finalization state model on `inventory_jobs`, a specific error taxonomy for post-pipeline failures, stepwise progress recording, corrected cancellation routing, and **post-review corrections** that prevent metadata from misrepresenting completed operations.

**In scope (implemented):**

- Durable finalization metadata columns + domain enums
- `JobFinalizationTracker` with `job_status` parameter on `fail()`
- Separate exception boundaries for domain commit vs marker write vs artifact upload vs marker write
- `FINALIZATION_METADATA_WRITE_FAILED` for post-operation marker persistence failures
- Technical success vs operational finalization (job stays `SUCCEEDED` after terminalization when reconciliation fails)
- Operational pointer invariant preserved
- Failure-reporting fallback with critical structured logging when job repo is unavailable
- `JobDetailResponse` for GET job detail with timestamps + sanitized error metadata
- Focused test suite + correction tests (A–J)

**Explicitly not implemented (deferred to Phase 3.3+):**

- Recovery command, artifact outbox, automatic retries, UI recovery, large executor refactor

## 2. Finalization state model

Two concepts are modeled separately:

| Concept | Field | Enum |
| ------- | ----- | ---- |
| Overall finalization lifecycle | `finalization_status` | `NOT_STARTED`, `IN_PROGRESS`, `FAILED`, `COMPLETED`, `CANCELED` |
| Step currently executing | `current_finalization_step` | `PERSIST_DOMAIN_RESULTS`, `PUBLISH_ARTIFACTS`, `TERMINALIZE_JOB`, `PROMOTE_OPERATIONAL_RESULT`, `UPDATE_AISLE`, `RECONCILE_INVENTORY` |
| Last step completed successfully | `last_completed_finalization_step` | `NONE`, `DOMAIN_RESULTS_PERSISTED`, …, `INVENTORY_RECONCILED` |

Additional fields: `finalization_error_code`, `finalization_error_metadata` (errors only), timestamps (`finalization_started_at`, `finalization_completed_at`, `domain_persisted_at`, `artifacts_published_at`).

Success artifact kinds live in `result_json.durable_artifacts` after terminalization — **not** in `finalization_error_metadata`.

## 3. Error taxonomy

| Code | When used |
| ---- | --------- |
| `DOMAIN_PERSISTENCE_FAILED` | Persist UoW failure (includes recompute inside transaction) |
| `FINALIZATION_METADATA_WRITE_FAILED` | Marker persistence failed after upstream step succeeded |
| `ARTIFACT_STORE_UNAVAILABLE` | Store unavailable before upload |
| `ARTIFACT_PUBLISH_FAILED` | Required artifact upload failure |
| `ARTIFACT_PUBLISH_PARTIAL` | Partial required artifact upload |
| `JOB_TERMINALIZATION_FAILED` | Job row terminal save failed after artifacts |
| `OPERATIONAL_PROMOTION_FAILED` | Promotion rejected or raised (job already `SUCCEEDED`) |
| `AISLE_RECONCILIATION_FAILED` | Aisle update failed (job stays `SUCCEEDED`) |
| `INVENTORY_RECONCILIATION_FAILED` | Inventory reconcile failed (job stays `SUCCEEDED`) |
| `FINALIZATION_CANCELED` | Effective cancellation during finalization |

## 4. Corrected exception boundaries

### Domain persistence vs marker

```python
try:
    persist_use_case.execute(...)   # UoW commit
except Exception:
    DOMAIN_PERSISTENCE_FAILED

try:
    tracker.record_domain_persisted()
except Exception:
    FINALIZATION_METADATA_WRITE_FAILED
    metadata: domain_commit_completed=true, verification_required=true
```

### Artifact upload vs marker

```python
try:
    durable_meta = publish_worker_durables(...)
except Artifact*Error:
    specific artifact codes

try:
    tracker.record_artifacts_published()
except Exception:
    FINALIZATION_METADATA_WRITE_FAILED
    metadata: artifact_upload_completed=true, published_artifact_kinds=[...]
```

## 5. Technical success vs operational finalization

**Technical success** (job may become `FAILED` if this fails):

- Domain persisted (UoW committed)
- Required artifacts uploaded
- Job row saved as `SUCCEEDED` (`_terminalize_job_row`)

**Operational finalization** (job remains `SUCCEEDED`; `finalization_status=FAILED` on failure):

- Operational promotion
- Aisle `PROCESSED` update
- Inventory reconciliation

`finalization_status=COMPLETED` only after inventory reconciliation succeeds.

## 6. Operational pointer invariant

```text
if aisle.operational_job_id == job.id:
    job.status must equal SUCCEEDED
```

Post-promotion reconciliation failures keep `job.status=SUCCEEDED` so the invariant holds when promotion succeeded. Promotion failures leave the job non-operational (`operational_job_id != job.id`).

## 7. Job status behavior by failing step

| Failing step | `job.status` | `finalization_status` |
| ------------ | ------------ | --------------------- |
| Persist UoW | `FAILED` | `FAILED` |
| Domain marker write | `FAILED` | `FAILED` |
| Artifact upload | `FAILED` | `FAILED` |
| Artifact marker write | `FAILED` | `FAILED` |
| Terminalization | `FAILED` | `FAILED` |
| Promotion / aisle / inventory | `SUCCEEDED` | `FAILED` |
| Full success | `SUCCEEDED` | `COMPLETED` |

## 8. Failure-reporting fallback

`report_finalization_failure()` critical-logs when `job_repo.save()` fails during failure recording. `fail_finalization_and_aisle()` continues to mark the aisle failed even when job metadata cannot be persisted. The critical log includes `job_id`, error code, step, and `known_last_completed_step`. Callers must not assume durable failure metadata was saved when reporting fails.

## 9. Known crash windows

| Window | Risk |
| ------ | ---- |
| UoW commit → `record_domain_persisted()` | Rows committed, marker absent |
| Artifact upload → `record_artifacts_published()` | Artifacts durable, marker absent |
| In-memory job repo | Object mutated before failed save (SQL repos differ) |

Recovery must verify by `job_id` when `verification_required=true`.

## 10. Cancellation policy

Unchanged from initial 3.2: pre-commit cancel → `CANCELED`, no rows; post-commit cancel → `CANCELED`, rows retained, no artifacts.

## 11. API visibility

- `JobSummary`: compact finalization fields (list/status endpoints)
- `JobDetailResponse`: adds timestamps + sanitized `finalization_error_metadata`
- GET `.../jobs/{job_id}` returns `JobDetailResponse`

## 12. Tests added/updated

| Test | Coverage |
| ---- | -------- |
| corr A | Domain marker failure → `FINALIZATION_METADATA_WRITE_FAILED` |
| corr B | Artifact marker failure after upload |
| corr C/D | Aisle/inventory failure → job `SUCCEEDED`, finalization `FAILED` |
| corr E | Promotion hard fail → job `SUCCEEDED`, not operational |
| corr F | Terminalization fail → job `FAILED` (existing T07) |
| corr G | Critical log when failure reporting save fails |
| corr H | Operational pointer invariant helper |
| corr I | Error metadata empty on success; artifacts in `result_json` |
| corr J | Happy path regression (T10) |

## 13. Behavioral matrix

| Failure point | Job status | Finalization status | Last completed step | Operational pointer allowed |
| ------------- | ---------- | ------------------- | ------------------- | --------------------------- |
| Domain UoW failure | `FAILED` | `FAILED` | `NONE` | No |
| Domain marker failure after commit | `FAILED` | `FAILED` | prior / verification required | No |
| Artifact upload failure | `FAILED` | `FAILED` | `DOMAIN_RESULTS_PERSISTED` | No |
| Artifact marker failure after upload | `FAILED` | `FAILED` | verification required | No |
| Terminalization failure | `FAILED` | `FAILED` | `ARTIFACTS_PUBLISHED` | No |
| Promotion failure | `SUCCEEDED` | `FAILED` | `JOB_TERMINALIZED` | No |
| Aisle update failure | `SUCCEEDED` | `FAILED` | `OPERATIONAL_RESULT_PROMOTED` | Yes (if promoted) |
| Inventory reconcile failure | `SUCCEEDED` | `FAILED` | `AISLE_UPDATED` | Yes (if promoted) |
| Success | `SUCCEEDED` | `COMPLETED` | `INVENTORY_RECONCILED` | Yes |

## 14. Deferred work (Phase 3.3+)

- Targeted recovery command
- Artifact outbox / automatic retries
- SQL integration validation under concurrency
- Executor decomposition

## Appendix: Is `DOMAIN_RESULTS_PERSISTED` transactional?

**No — post-UoW marker.** Written in a separate save after UoW commit. Marker write failures are classified as `FINALIZATION_METADATA_WRITE_FAILED` with `domain_commit_completed=true`, not `DOMAIN_PERSISTENCE_FAILED`.
