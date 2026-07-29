# Phase 5 — Alert catalog

| Alerta | Condición | Duración | Severidad | Runbook |
| ------ | --------- | -------- | --------- | ------- |
| api_not_ready | `/ready != 200` | 2m | critical | operational-runbooks.md §1 |
| sql_unavailable | ready reason REPOSITORY_BACKEND_UNAVAILABLE | 2m | critical | §2 |
| queue_depth_high | pending jobs > warn threshold | 5m | warning | §5 |
| queue_depth_critical | pending jobs > critical | 5m | critical | §5 |
| job_stuck | expired RUNNING leases > 0 sustained | 5m | critical | §4 |
| worker_no_heartbeat | worker_last_heartbeat age > lease window | 2m | critical | §3 |
| lease_loss_elevated | rate(job_lease_lost_total) high | 15m | warning | §6 |
| stale_write_rate | rate(job_stale_write_rejected_total) high with stale jobs | 15m | warning | §6 |
| http_5xx_rate | rate(http_response_errors_total{status_class="5xx"}) | 5m | critical | §1 |
| provider_degraded | provider_errors_total ratio | 15m | warning | §8 |
| outbox_blocked | artifact_outbox_pending / failed growth | 15m | critical | §7 |
| upload_failures | upload_rejected_total / upload_requests_total | 15m | warning | §9 |
| finalization_failures | job_finalization_failures_total rate | 15m | critical | §10 |
| operational_job_inconsistent | consistency finding OPERATIONAL_JOB_NOT_SUCCEEDED | 10m | critical | §10 |
| recovery_failed | job_recovery failures | 15m | warning | §11 |

## Silencing

- Silence single-job noise: alerts use rates/thresholds, not individual failures.
- Maintenance: pause scrape / inhibit by `environment` label.
- Never silence `sql_unavailable` without an incident ticket.

## Mapping

Declarative owners also live in `backend/src/runtime/production_alerts.py` (updated metric names align with this catalog).
