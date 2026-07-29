# Phase 5 — Metrics catalog

| Nombre | Tipo | Labels | Fuente | Uso | Alerta |
| ------ | ---- | ------ | ------ | --- | ------ |
| http_requests_total | counter | method, route_template, status_class | ObservabilityMiddleware | API rate | http_5xx_rate |
| http_request_duration_seconds | histogram | method, route_template, status_class | ObservabilityMiddleware | Latency | p95 degradation |
| http_requests_in_progress | gauge | method, route_template | ObservabilityMiddleware | Saturation | — |
| http_response_errors_total | counter | method, route_template, status_class | ObservabilityMiddleware | Errors | http_5xx_rate |
| job_lease_acquire_total | counter | operation, outcome | job_lease_metrics → registry | Lease | — |
| job_lease_renew_total | counter | operation, outcome | lease renew | Lease | — |
| job_lease_lost_total | counter | operation, outcome | lease loss | Fencing | lease_loss_elevated |
| job_stale_write_rejected_total | counter | operation, outcome | fencing CAS | Fencing | stale_write_rate |
| job_lease_reacquire_total | counter | operation, outcome | reacquire | Lease | — |
| jobs_stale_total | counter | job_type, outcome | JobStaleReconciler | Stale-fail | job_stuck |
| jobs_failed_total | counter | job_type, outcome, failure_code | instruments | Failures | terminal_failure_rate |
| jobs_completed_total | counter | job_type, outcome | instruments | Success | job_success_sli |
| provider_requests_total | counter | provider, operation, outcome | instruments | Providers | provider_degraded |
| provider_errors_total | counter | provider, operation, outcome, error_class | instruments | Providers | provider_degraded |
| provider_timeouts_total | counter | provider, operation, outcome | instruments | Providers | provider_timeouts |
| artifact_publication_total | counter | outcome, artifact_kind, storage_backend | instruments | Artifacts | outbox_blocked |
| job_finalization_stage_total | counter | stage, outcome, reason | instruments | Finalization | finalization_failures |
| job_finalization_stage_duration_seconds | histogram | stage, outcome, reason | instruments | Finalization | finalization_slow |
| jobs_in_state | gauge | status, job_type | SQL aggregate (ops) | Queue | queue_depth_* |
| job_active_leases | gauge | — | SQL aggregate (ops) | Leases | — |
| job_expired_running_leases | gauge | — | SQL aggregate (ops) | Stale | job_stuck |
| artifact_outbox_pending | gauge | — | SQL aggregate (ops) | Outbox | outbox_blocked |
| worker_process_up | gauge | worker_role, environment | worker bootstrap | Workers | worker_no_heartbeat |
| worker_last_heartbeat_timestamp | gauge | worker_role, environment | monitoring | Workers | worker_no_heartbeat |

Gauges derived from SQL should be refreshed on a short cache / scrape helper — not per-request full scans.
