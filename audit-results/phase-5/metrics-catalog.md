# Phase 5 — Metrics catalog

Status column: `IMPLEMENTED` | `PLANNED` | `DEPRECATED`

| Nombre | Tipo | Labels | Fuente | Status | Alerta |
| ------ | ---- | ------ | ------ | ------ | ------ |
| http_requests_total | counter | method, route_template, status_class | ObservabilityMiddleware | IMPLEMENTED | Http5xxRateHigh |
| http_request_duration_seconds | histogram | method, route_template, status_class | ObservabilityMiddleware | IMPLEMENTED | — |
| http_requests_in_progress | gauge | method, route_template | ObservabilityMiddleware | IMPLEMENTED | — |
| http_response_errors_total | counter | method, route_template, status_class | ObservabilityMiddleware | IMPLEMENTED | Http5xxRateHigh |
| observability_series_rejected_total | counter | reason_code | MetricsRegistry | IMPLEMENTED | — |
| job_lease_acquire_total | counter | operation, outcome | job_lease_metrics | IMPLEMENTED | — |
| job_lease_renew_total | counter | operation, outcome | lease renew | IMPLEMENTED | — |
| job_lease_lost_total | counter | operation, outcome | lease loss | IMPLEMENTED | LeaseLossElevated |
| job_stale_write_rejected_total | counter | operation, outcome | fencing CAS | IMPLEMENTED | StaleWriteRejectionElevated |
| job_lease_reacquire_total | counter | operation, outcome | reacquire | IMPLEMENTED | — |
| jobs_created_total | counter | job_type, outcome | AisleJobLaunchService | IMPLEMENTED | — |
| jobs_stale_total | counter | job_type, outcome | JobStaleReconciler / RecoverStaleJob | IMPLEMENTED | JobExpiredRunningLeases |
| jobs_failed_total | counter | job_type, outcome, failure_code | instruments | PLANNED | — |
| jobs_completed_total | counter | job_type, outcome | instruments | PLANNED | — |
| jobs_canceled_total | counter | job_type, outcome | instruments | PLANNED | — |
| jobs_retried_total | counter | job_type, outcome | launch (retry_of) | IMPLEMENTED | — |
| jobs_recovered_total | counter | job_type, outcome | RecoverStaleJobUseCase | IMPLEMENTED | — |
| jobs_started_total | counter | job_type, outcome | instruments | PLANNED | — |
| job_processing_duration_seconds | histogram | job_type | instruments | PLANNED | — |
| job_queue_wait_duration_seconds | histogram | job_type | instruments | PLANNED | — |
| provider_requests_total | counter | provider, operation, outcome | gemini/openai adapters | IMPLEMENTED | ProviderErrorRatioHigh |
| provider_request_duration_seconds | histogram | provider, operation, outcome | adapters | IMPLEMENTED | — |
| provider_errors_total | counter | provider, operation, outcome, error_class | adapters | IMPLEMENTED | ProviderErrorRatioHigh |
| provider_timeouts_total | counter | provider, operation, outcome | adapters | IMPLEMENTED | — |
| provider_retries_total | counter | provider, operation, outcome | instruments | PLANNED | — |
| upload_requests_total | counter | outcome | instruments | PLANNED | — |
| upload_bytes_total | counter | outcome | instruments | PLANNED | — |
| upload_rejected_total | counter | outcome | instruments | PLANNED | — |
| artifact_publication_total | counter | outcome, artifact_kind, storage_backend | instruments | PLANNED | ArtifactOutboxBlocked |
| artifact_publication_duration_seconds | histogram | … | instruments | PLANNED | — |
| artifact_publication_retry_total | counter | … | instruments | PLANNED | — |
| job_finalization_stage_total | counter | stage, outcome, reason | FinalizationStageRecorder | IMPLEMENTED | FinalizationFailuresElevated |
| job_finalization_stage_duration_seconds | histogram | stage, outcome, reason | FinalizationStageRecorder | IMPLEMENTED | — |
| job_finalization_failures_total | counter | stage, outcome, reason | FinalizationStageRecorder | IMPLEMENTED | FinalizationFailuresElevated |
| jobs_in_state | gauge | status, job_type | OperationalMetricsCollector | IMPLEMENTED | QueueDepthHigh/Critical |
| job_active_leases | gauge | — | OperationalMetricsCollector | IMPLEMENTED | — |
| job_expired_running_leases | gauge | — | OperationalMetricsCollector | IMPLEMENTED | JobExpiredRunningLeases |
| artifact_outbox_pending | gauge | — | OperationalMetricsCollector | IMPLEMENTED | ArtifactOutboxBlocked |
| artifact_outbox_failed | gauge | — | OperationalMetricsCollector | IMPLEMENTED | ArtifactOutboxBlocked |
| worker_process_up | gauge | worker_role, environment | run_worker | IMPLEMENTED | WorkerProcessDown |
| worker_last_heartbeat_timestamp | gauge | worker_role, environment | instruments | PLANNED | — |
| worker_jobs_active | gauge | … | instruments | PLANNED | — |
| worker_jobs_started_total | counter | … | instruments | PLANNED | — |
| worker_shutdown_total | counter | … | instruments | PLANNED | — |
| repository_operations_total | counter | … | instruments | PLANNED | — |
| sql_* | counter | … | instruments | PLANNED | — |
| job_recovery_total | counter | outcome | instruments | PLANNED | — (do not alert; use stale_recovery_scheduler_*) |
| stale_recovery_scheduler_runs_total | counter | outcome | StaleJobRecoveryScheduler | IMPLEMENTED | RecoverySchedulerFailures |
| stale_recovery_scheduler_recovered_total | counter | outcome | StaleJobRecoveryScheduler | IMPLEMENTED | — |
| operational_metrics_collector_errors_total | counter | reason_code | OperationalMetricsCollector | IMPLEMENTED | OperationalMetricsCollectorErrors |

Cardinality: unmatched HTTP routes use `__unmatched__`; series capped by `METRICS_MAX_SERIES_PER_METRIC` (default 500).
