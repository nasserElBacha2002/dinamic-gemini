# Phase 5 — SLI / SLO proposal (non-contractual)

## SLIs

| SLI | Formula |
| --- | ------- |
| API availability | `success = http 2xx+3xx+4xx(non-5xx) on ready backends` / total (exclude `/metrics`,`/health` noise as needed) |
| Job success rate | `jobs_completed / (completed+failed)` excluding `CANCELED`, `INVALID_INPUT`, admin/test job types |
| Job processing latency | histogram quantile of `job_processing_duration_seconds` |
| Queue wait latency | `job_queue_wait_duration_seconds` quantile |
| Artifact publication success | `artifact_publication_total{outcome="ok"} / all outcomes` |
| Provider availability | `provider_requests_total{outcome="ok"} / all` by provider |

## Initial SLO targets (proposal)

| Objective | Target | Window |
| --------- | ------ | ------ |
| Valid jobs succeed | 99% | 30 days |
| API availability | 99.5% | 30 days |
| Artifact publication success | 99% | 30 days |
| p95 job processing (median tenant) | track baseline first quarter | 30 days |

Exclusions: user cancel, invalid input, auth failures, synthetic tests, admin-only jobs.

These are **operational proposals**, not commercial commitments.
