# Phase 5 — Alert catalog

Deployable rules: `deploy/prometheus/dinamic-phase5-alerts.yml`  
Tests: `deploy/prometheus/tests/phase5_alerts.test.yml` (`promtool check/test rules`)

| Alerta (Prometheus) | Condición (resumen) | for | severity | Runbook |
| ------------------- | ------------------- | --- | -------- | ------- |
| Http5xxRateHigh | 5xx / requests > 5% | 5m | critical | operational-runbooks.md#http-5xx |
| JobExpiredRunningLeases | `job_expired_running_leases > 0` | 5m | critical | #job-stuck |
| QueueDepthHigh | queued process_aisle > 50 | 5m | warning | #queue-depth |
| QueueDepthCritical | queued > 200 | 5m | critical | #queue-depth |
| LeaseLossElevated | rate(job_lease_lost_total[15m]) > 0.1 | 15m | warning | #lease-loss |
| StaleWriteRejectionElevated | rate(stale_write) > 0.2 | 15m | warning | #stale-write |
| ProviderErrorRatioHigh | errors/requests > 20% | 15m | warning | #provider-degraded |
| ArtifactOutboxBlocked | pending > 100 or failed > 10 | 15m | critical | #outbox-blocked |
| FinalizationFailuresElevated | rate(failures) > 0.05 | 15m | critical | #finalization |
| WorkerProcessDown | max(worker_process_up) < 1 | 2m | critical | #worker-heartbeat |
| RecoverySchedulerFailures | rate(non-recovered recovery) > 0.05 | 15m | warning | #recovery |
| OperationalMetricsCollectorErrors | collector error rate > 0 | 10m | warning | #gauges |

Thresholds are conservative defaults; tune after baseline. Do not scrape `/metrics` from browsers with API keys.
