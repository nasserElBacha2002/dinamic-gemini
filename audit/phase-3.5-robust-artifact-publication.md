# Phase 3.5 — Robust Artifact Publication (Corrections)

## Summary

Phase 3.5 makes artifact publication **autonomous, crash-safe, and durable**. Required artifacts are staged to exact durable bytes before outbox registration; an independent outbox worker executes retries without the original `V3JobExecutor`; finalization continues from `job_id` and durable state only.

## Architecture

| Component | Responsibility |
| --- | --- |
| `artifact_publication_outbox` | Work queue — retry state, leases, checksum fields |
| `job_artifact_manifest` | Published artifact state + verification level |
| `ArtifactStagingStore` | Exact-byte durable staging (`artifact-staging/{job_id}/{kind}/{sha256}`) |
| `ArtifactPublicationDispatcher` | Stage/register, claim, verify (SHA-256), upload, manifest + outbox updates |
| `ArtifactPublicationOutboxWorker` | Autonomous poll loop — `release → claim due → publish → continue` |
| `ArtifactPublicationStateReconciler` | Repairs manifest/outbox split writes after crash windows |
| `AutomaticFinalizationContinuationUseCase` | `continue_finalization(job_id)` — no worker context |

Flow after domain commit:

```text
generate artifact → stage exact bytes → register outbox (EXACT_DURABLE_SOURCE)
→ claim → verify SHA-256 → upload if needed → manifest PUBLISHED → outbox PUBLISHED
→ REQUIRED_ARTIFACTS completed → automatic finalization continuation
```

## Autonomous worker

Deploy:

```bash
python -m src.jobs.artifact_publication_worker
```

Env:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARTIFACT_PUBLICATION_WORKER_ENABLED` | `false` | Enable worker process |
| `ARTIFACT_PUBLICATION_POLL_SECONDS` | `5` | Idle poll interval |
| `ARTIFACT_PUBLICATION_BATCH_SIZE` | `10` | Max rows claimed per poll |
| `ARTIFACT_STAGING_BASE_PATH` | `data/artifact-staging` | Durable staging root |

Eligible outbox rows: `PENDING`, `RETRY_SCHEDULED` (due), `CLAIMED` (expired lease).

## Deployment

**Required migration order:** `0040_artifact_publication_outbox.sql` → `0041_artifact_publication_durable_sources_and_checksums.sql`

**Process topology:**

```text
V3JobExecutor (inline first pass) ──► stages + registers outbox
ArtifactPublicationOutboxWorker ─────► autonomous retries + continuation
Manual recovery ───────────────────► verify / retry_now / resume (unchanged)
```

## Source lifecycle

| Source | Durable | Survives restart | Exact | Cleanup condition |
| --- | ---: | ---: | ---: | --- |
| execution_log staging | Yes | Yes | Yes | After confirmed publication (policy TBD) |
| hybrid_report_json staging | Yes | Yes | Yes | After confirmed publication (policy TBD) |
| hybrid_report_csv | Optional | Local/reconstructable | If present | Optional; does not block required set |

Staging failure → `ARTIFACT_SOURCE_STAGING_FAILED`; **no** retryable outbox row for missing local bytes.

## State semantics

| State | Job status | Finalization status | UI | Automatic action |
| --- | --- | --- | --- | --- |
| Pending initial publication | RUNNING | IN_PROGRESS | Publicando artefactos | Worker/dispatcher claims |
| Retry scheduled | RUNNING | IN_PROGRESS | Reintentando publicación | Outbox worker at `next_attempt_at` |
| Claimed | RUNNING | IN_PROGRESS | Publicando artefactos | Publish or lease expiry reclaim |
| Published required set | RUNNING → SUCCEEDED | IN_PROGRESS → COMPLETED | Completado | Automatic continuation |
| Permanent failure | FAILED | FAILED | Error definitivo | Admin recovery only |
| Source conflict | FAILED / inconsistent | FAILED | Conflicto de origen | Investigation required |

Retry-pending jobs are **not** terminal failures. Stale reconciler skips jobs with active retryable outbox work.

## Checksum model

Separate fields: `source_sha256`, `storage_etag`, `storage_checksum_value`, `storage_checksum_algorithm`, `verified_at`, `verification_level`.

Verification priority: remote SHA-256 metadata → confirmed; known-algorithm checksum → confirmed; size only → `POSITIVE_EVIDENCE_ONLY` (not confirmed).

## Typed error classification

Programming errors (`NameError`, `TypeError`, …) → `internal_publication_error`, non-retryable. Transient network/storage → retryable. Unknown exceptions default non-retryable unless evidence of transience.

## SQL migration 0041

Adds checksum columns, status/source_type CHECK constraints, due-work index `IX_artifact_publication_outbox_due_work`. Does not modify deployed `0040`.

Foreign keys: intentionally omitted so outbox/manifest evidence can survive job cleanup (documented policy).

## API visibility

`artifact_publication` block on job detail; degrades to `null` with warning log when migration/store unavailable (`MissingMigrationOrStoreUnavailableError`).

## Tests

- `test_worker_phase3_part5_artifact_outbox.py` — inline dispatcher / executor integration
- `test_worker_phase3_part5_artifact_outbox_worker.py` — autonomous worker, staging, continuation, checksum, stale skip, API degrade

SQL integration: concurrent claim / migration 0041 tests skip when SQL Server unavailable.

## Remaining limitations

- Staging cleanup after publication not automated
- SQL integration tests require live SQL Server + migrations applied
- Frontend copy for retry vs permanent failure may need localized strings update

## Explicit non-goals (confirmed)

- No provider re-execution
- No domain persistence replay
- No automatic full-job retry
