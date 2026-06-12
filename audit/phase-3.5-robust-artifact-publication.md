# Phase 3.5 — Robust Artifact Publication

## Summary

Phase 3.5 introduces a durable **artifact publication outbox** so required worker artifacts can be published reliably through transient storage failures without re-running the provider, normalization, or domain persistence.

## Architecture

| Component | Responsibility |
| --- | --- |
| `artifact_publication_outbox` | Authoritative **work queue** — what still needs publishing, retry state, leases |
| `job_artifact_manifest` | Authoritative **artifact state** — current published/failed status per kind |
| `ArtifactPublicationDispatcher` | Claims work, resolves local source, uploads/verifies, updates manifest + outbox |
| `ArtifactFinalizationContinuationCoordinator` | Idempotent continuation of terminalization → promotion → reconciliation |

Flow after domain commit:

```text
ensure manifest entries
→ register outbox work (durable intent)
→ dispatch (claim → upload/verify → manifest PUBLISHED → outbox PUBLISHED)
→ REQUIRED_ARTIFACTS completed
→ finalization continuation (no provider replay)
```

## Source durability policy

| Artifact | Required | Durable source | Retryable | Reconstruction allowed |
| --- | ---: | --- | ---: | --- |
| execution_log | Yes | EXACT_LOCAL_SOURCE (run_dir file) | Yes | No — do not fabricate from DB events |
| hybrid_report_json | Yes | EXACT_LOCAL_SOURCE / report_path | Yes | No — do not rebuild from domain rows |
| hybrid_report_csv | No | RECONSTRUCTABLE if deterministic | Yes | Yes — optional; absence does not block required set |

Ephemeral worker directories: publication intent is recorded while local sources exist; if sources are gone before retry, required artifacts move to `PERMANENTLY_FAILED` (`source_missing`).

## Deterministic keys

Logical storage keys remain:

```text
jobs/{job_id}/run/{filename}
```

Retries reuse the same key; confirmed existing objects skip re-upload when size matches.

## Retry matrix

| Failure | Retry | Final state |
| --- | ---: | --- |
| Storage timeout | Yes | RETRY_SCHEDULED |
| Source missing | No | PERMANENTLY_FAILED |
| Object mismatch | No | PERMANENTLY_FAILED |
| Max attempts exceeded | No | PERMANENTLY_FAILED |

Defaults (configurable via env):

- `ARTIFACT_PUBLICATION_MAX_ATTEMPTS=5`
- `ARTIFACT_PUBLICATION_LEASE_SECONDS=120`
- `ARTIFACT_PUBLICATION_BACKOFF_SECONDS=0,30,120,600,1800`

## Claim / lease strategy

- SQL: `UPDLOCK + ROWLOCK` on claim; expired leases released to `PENDING` / `RETRY_SCHEDULED`
- Memory store mirrors semantics for tests
- One active claim per `(job_id, artifact_kind)` row

## Crash recovery

| Window | Behavior |
| --- | --- |
| Crash after upload, before manifest | Next dispatch sees object in storage → confirms without upload → updates manifest + outbox |
| Crash after manifest, before outbox | Next dispatch reconciles outbox to PUBLISHED without upload |
| Crash mid-claim | Lease expires → row reclaimable |

Partial publication is preserved: successful artifacts stay `PUBLISHED`; failed required kinds remain retryable or permanently failed.

## Finalization continuation

When all required manifest entries are `PUBLISHED` and verified, the dispatcher calls `tracker.record_artifacts_published()` then `ArtifactFinalizationContinuationCoordinator.continue_if_required_complete()` which reuses existing `V3JobExecutionStateService.finalize_success()` — no duplicated terminalization logic.

## Manual recovery compatibility

Admin recovery (`verify`, `republish`, `resume`) remains unchanged. Outbox upsert is idempotent on `(job_id, artifact_kind)` — manual operations do not create duplicate logical rows.

## API visibility

`GET .../jobs/{job_id}` includes optional `artifact_publication` block with required counts, retry/permanent failure counts, next attempt, and per-item sanitized status.

## Retention

- Published outbox rows retained for audit
- Temporary local sources should remain until required publication confirmed (worker run_dir policy unchanged)

## Tests

`tests/infrastructure/pipeline/test_worker_phase3_part5_artifact_outbox.py` — 17 tests covering outbox registration, publication, partial failure, retry/permanent classification, claim/lease, skip-upload, continuation idempotency, executor integration, crash reconciliation, SQL concurrency (skipped when SQL/migration unavailable).

## Known limitations

- No background scheduler — retries occur on next worker dispatch or manual recovery
- SQL integration tests require migration `0040_artifact_publication_outbox.sql` applied
- Optional CSV outbox row created only when local file exists at registration time

## Explicit non-goals (confirmed)

- No provider re-execution
- No domain persistence replay
- No automatic full-job retry
- No UI redesign
