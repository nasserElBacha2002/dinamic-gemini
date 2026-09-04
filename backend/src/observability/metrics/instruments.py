"""Phase 5 — named metrics instruments (single registry)."""

from __future__ import annotations

from src.observability.metrics.registry import get_metrics_registry

# HTTP
HTTP_REQUESTS_TOTAL = "http_requests_total"
HTTP_REQUEST_DURATION_SECONDS = "http_request_duration_seconds"
HTTP_REQUESTS_IN_PROGRESS = "http_requests_in_progress"
HTTP_RESPONSE_ERRORS_TOTAL = "http_response_errors_total"

# Jobs
JOBS_CREATED_TOTAL = "jobs_created_total"
JOBS_STARTED_TOTAL = "jobs_started_total"
JOBS_COMPLETED_TOTAL = "jobs_completed_total"
JOBS_FAILED_TOTAL = "jobs_failed_total"
JOBS_CANCELED_TOTAL = "jobs_canceled_total"
JOBS_RETRIED_TOTAL = "jobs_retried_total"
JOBS_RECOVERED_TOTAL = "jobs_recovered_total"
JOBS_STALE_TOTAL = "jobs_stale_total"
JOBS_IN_STATE = "jobs_in_state"
JOB_PROCESSING_DURATION_SECONDS = "job_processing_duration_seconds"
JOB_QUEUE_WAIT_DURATION_SECONDS = "job_queue_wait_duration_seconds"

# Leases (aligned with Phase 3 names)
JOB_LEASE_ACQUIRE_TOTAL = "job_lease_acquire_total"
JOB_LEASE_RENEW_TOTAL = "job_lease_renew_total"
JOB_LEASE_LOST_TOTAL = "job_lease_lost_total"
JOB_STALE_WRITE_REJECTED_TOTAL = "job_stale_write_rejected_total"
JOB_LEASE_REACQUIRE_TOTAL = "job_lease_reacquire_total"
JOB_ACTIVE_LEASES = "job_active_leases"
JOB_EXPIRED_RUNNING_LEASES = "job_expired_running_leases"

# Worker
WORKER_PROCESS_UP = "worker_process_up"
WORKER_LAST_HEARTBEAT_TIMESTAMP = "worker_last_heartbeat_timestamp"
WORKER_JOBS_ACTIVE = "worker_jobs_active"
WORKER_JOBS_STARTED_TOTAL = "worker_jobs_started_total"
WORKER_JOBS_COMPLETED_TOTAL = "worker_jobs_completed_total"
WORKER_JOBS_FAILED_TOTAL = "worker_jobs_failed_total"
WORKER_SHUTDOWN_TOTAL = "worker_shutdown_total"
WORKER_ABORT_TOTAL = "worker_abort_total"

# Providers
PROVIDER_REQUESTS_TOTAL = "provider_requests_total"
PROVIDER_REQUEST_DURATION_SECONDS = "provider_request_duration_seconds"
PROVIDER_ERRORS_TOTAL = "provider_errors_total"
PROVIDER_TIMEOUTS_TOTAL = "provider_timeouts_total"
PROVIDER_RETRIES_TOTAL = "provider_retries_total"

# Uploads / artifacts
UPLOAD_REQUESTS_TOTAL = "upload_requests_total"
UPLOAD_BYTES_TOTAL = "upload_bytes_total"
UPLOAD_REJECTED_TOTAL = "upload_rejected_total"
UPLOAD_PROCESSING_DURATION_SECONDS = "upload_processing_duration_seconds"
ARTIFACT_PUBLICATION_TOTAL = "artifact_publication_total"
ARTIFACT_PUBLICATION_DURATION_SECONDS = "artifact_publication_duration_seconds"
ARTIFACT_PUBLICATION_RETRY_TOTAL = "artifact_publication_retry_total"
ARTIFACT_OUTBOX_PENDING = "artifact_outbox_pending"
ARTIFACT_OUTBOX_FAILED = "artifact_outbox_failed"

# Artifact storage fetch (low-cardinality labels only — never asset_id/object_key)
STORAGE_FETCH_DURATION_SECONDS = "storage_fetch_duration_seconds"
STORAGE_FETCH_SLOW_TOTAL = "storage_fetch_slow_total"
STORAGE_FETCH_FAILED_TOTAL = "storage_fetch_failed_total"

# SQL / repository
REPOSITORY_OPERATIONS_TOTAL = "repository_operations_total"
REPOSITORY_OPERATION_DURATION_SECONDS = "repository_operation_duration_seconds"
SQL_CONNECTION_FAILURES_TOTAL = "sql_connection_failures_total"
SQL_TIMEOUTS_TOTAL = "sql_timeouts_total"
SQL_DEADLOCKS_TOTAL = "sql_deadlocks_total"
SQL_TRANSACTION_ROLLBACKS_TOTAL = "sql_transaction_rollbacks_total"
REPOSITORY_BACKEND_MODE = "repository_backend_mode"

# Finalization
JOB_FINALIZATION_STAGE_DURATION_SECONDS = "job_finalization_stage_duration_seconds"
JOB_FINALIZATION_STAGE_TOTAL = "job_finalization_stage_total"
JOB_FINALIZATION_FAILURES_TOTAL = "job_finalization_failures_total"

# Recovery
JOB_RECOVERY_TOTAL = "job_recovery_total"
JOB_RECOVERY_DURATION_SECONDS = "job_recovery_duration_seconds"

# Positioning module (Phase 8)
POSITION_LABEL_DETECTION_TOTAL = "position_label_detection_total"
POSITION_LABEL_DETECTION_DURATION_SECONDS = "position_label_detection_duration_seconds"
POSITION_LABEL_INVALID_SIGNATURE_TOTAL = "position_label_invalid_signature_total"
POSITION_RECONCILIATION_TOTAL = "position_reconciliation_total"
POSITION_RECONCILIATION_DURATION_SECONDS = "position_reconciliation_duration_seconds"
POSITION_RECONCILIATION_CONFLICT_TOTAL = "position_reconciliation_conflict_total"
POSITION_RECONCILIATION_UNASSIGNED_TOTAL = "position_reconciliation_unassigned_total"
POSITION_OVERRIDE_TOTAL = "position_override_total"
POSITION_OVERRIDE_CONFLICT_TOTAL = "position_override_conflict_total"
POSITION_OVERRIDE_DURATION_SECONDS = "position_override_duration_seconds"
POSITIONING_OPERATIONAL_VIEW_DURATION_SECONDS = "positioning_operational_view_duration_seconds"
POSITIONING_REPROCESS_TOTAL = "positioning_reprocess_total"
POSITIONING_REPROCESS_FAILURE_TOTAL = "positioning_reprocess_failure_total"
PROCESSING_RECOVERY_TOTAL = "processing_recovery_total"
PROCESSING_RECOVERY_FAILURE_TOTAL = "processing_recovery_failure_total"
PROCESSING_STALE_JOBS_TOTAL = "processing_stale_jobs_total"


def observe_http_request(
    *,
    method: str,
    route_template: str,
    status_class: str,
    duration_seconds: float,
) -> None:
    reg = get_metrics_registry()
    labels = {
        "method": method.upper(),
        "route_template": route_template,
        "status_class": status_class,
    }
    reg.inc(HTTP_REQUESTS_TOTAL, "Total HTTP requests", labels)
    reg.observe(
        HTTP_REQUEST_DURATION_SECONDS,
        "HTTP request latency in seconds",
        duration_seconds,
        labels,
    )
    if status_class in ("4xx", "5xx"):
        reg.inc(
            HTTP_RESPONSE_ERRORS_TOTAL,
            "HTTP error responses",
            {"method": method.upper(), "route_template": route_template, "status_class": status_class},
        )


def inc_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> None:
    """Bridge used by Phase 3 callers — single registry."""
    help_map = {
        JOB_LEASE_ACQUIRE_TOTAL: "Job lease acquire attempts",
        JOB_LEASE_RENEW_TOTAL: "Job lease renew attempts",
        JOB_LEASE_LOST_TOTAL: "Job lease lost events",
        JOB_STALE_WRITE_REJECTED_TOTAL: "Stale write rejections (fencing)",
        JOB_LEASE_REACQUIRE_TOTAL: "Job lease reacquire attempts",
    }
    get_metrics_registry().inc(
        name,
        help_map.get(name, "Job lease metric"),
        {"operation": operation, "outcome": outcome},
    )


def record_job_outcome(*, job_type: str, outcome: str, failure_code: str | None = None) -> None:
    reg = get_metrics_registry()
    labels = {"job_type": job_type or "unknown", "outcome": outcome}
    if outcome == "succeeded":
        reg.inc(JOBS_COMPLETED_TOTAL, "Jobs completed successfully", labels)
    elif outcome == "failed":
        fail_labels = {**labels, "failure_code": (failure_code or "unknown")[:64]}
        reg.inc(JOBS_FAILED_TOTAL, "Jobs failed", fail_labels)
    elif outcome == "canceled":
        reg.inc(JOBS_CANCELED_TOTAL, "Jobs canceled", labels)
    elif outcome == "stale":
        reg.inc(JOBS_STALE_TOTAL, "Jobs marked stale-failed", labels)
    elif outcome == "recovered":
        reg.inc(JOBS_RECOVERED_TOTAL, "Jobs recovered", labels)
    elif outcome == "retried":
        reg.inc(JOBS_RETRIED_TOTAL, "Jobs retried", labels)


def record_provider_call(
    *,
    provider: str,
    operation: str,
    outcome: str,
    duration_seconds: float,
    error_class: str | None = None,
) -> None:
    reg = get_metrics_registry()
    labels = {
        "provider": provider[:64],
        "operation": operation[:64],
        "outcome": outcome[:64],
    }
    reg.inc(PROVIDER_REQUESTS_TOTAL, "External provider requests", labels)
    reg.observe(
        PROVIDER_REQUEST_DURATION_SECONDS,
        "Provider request duration seconds",
        duration_seconds,
        labels,
    )
    if outcome != "ok":
        err = {**labels, "error_class": (error_class or outcome)[:64]}
        reg.inc(PROVIDER_ERRORS_TOTAL, "Provider errors", err)
        if (error_class or "").lower() == "timeout" or outcome == "timeout":
            reg.inc(PROVIDER_TIMEOUTS_TOTAL, "Provider timeouts", labels)


def record_storage_fetch(
    *,
    backend: str,
    outcome: str,
    duration_seconds: float,
    slow: bool = False,
) -> None:
    """Record storage get_object latency. Labels must stay low-cardinality."""
    reg = get_metrics_registry()
    labels = {
        "storage_backend": (backend or "unknown")[:32],
        "outcome": (outcome or "unknown")[:32],
    }
    reg.observe(
        STORAGE_FETCH_DURATION_SECONDS,
        "Artifact storage fetch duration seconds",
        max(0.0, float(duration_seconds)),
        labels,
    )
    if outcome != "ok":
        reg.inc(STORAGE_FETCH_FAILED_TOTAL, "Artifact storage fetch failures", labels)
    if slow:
        reg.inc(
            STORAGE_FETCH_SLOW_TOTAL,
            "Artifact storage fetches exceeding slow warning threshold",
            {"storage_backend": (backend or "unknown")[:32]},
        )


def record_finalization_stage(
    *,
    stage: str,
    outcome: str,
    duration_seconds: float,
    reason: str | None = None,
) -> None:
    reg = get_metrics_registry()
    labels = {"stage": stage[:64], "outcome": outcome[:64]}
    if reason:
        labels["reason"] = reason[:64]
    reg.inc(JOB_FINALIZATION_STAGE_TOTAL, "Job finalization stage outcomes", labels)
    reg.observe(
        JOB_FINALIZATION_STAGE_DURATION_SECONDS,
        "Job finalization stage duration seconds",
        duration_seconds,
        labels,
    )
    if outcome != "ok":
        reg.inc(JOB_FINALIZATION_FAILURES_TOTAL, "Job finalization failures", labels)


def record_positioning_operational_view(*, outcome: str, duration_seconds: float) -> None:
    get_metrics_registry().observe(
        POSITIONING_OPERATIONAL_VIEW_DURATION_SECONDS,
        "Positioning operational view duration seconds",
        duration_seconds,
        {"outcome": (outcome or "unknown")[:64]},
    )


def record_positioning_reprocess(*, mode: str, outcome: str) -> None:
    labels = {
        "mode": (mode or "unknown")[:64],
        "outcome": (outcome or "unknown")[:64],
    }
    reg = get_metrics_registry()
    reg.inc(POSITIONING_REPROCESS_TOTAL, "Positioning reprocess requests", labels)
    if outcome not in {"ok", "reused"}:
        reg.inc(
            POSITIONING_REPROCESS_FAILURE_TOTAL,
            "Positioning reprocess failures",
            labels,
        )


def record_processing_recovery(*, outcome: str, reason_code: str | None = None) -> None:
    labels = {"outcome": (outcome or "unknown")[:64]}
    if reason_code:
        labels["reason_code"] = reason_code[:64]
    reg = get_metrics_registry()
    reg.inc(PROCESSING_RECOVERY_TOTAL, "Processing recovery attempts", labels)
    if outcome not in {"ok", "noop"}:
        reg.inc(
            PROCESSING_RECOVERY_FAILURE_TOTAL,
            "Processing recovery failures",
            labels,
        )


def record_position_override(*, outcome: str, operation: str, duration_seconds: float) -> None:
    labels = {
        "outcome": (outcome or "unknown")[:64],
        "operation": (operation or "unknown")[:64],
    }
    reg = get_metrics_registry()
    reg.inc(POSITION_OVERRIDE_TOTAL, "Manual position override operations", labels)
    reg.observe(
        POSITION_OVERRIDE_DURATION_SECONDS,
        "Manual position override duration seconds",
        duration_seconds,
        labels,
    )
    if outcome == "conflict":
        reg.inc(POSITION_OVERRIDE_CONFLICT_TOTAL, "Manual position override conflicts", labels)


def record_position_reconciliation(
    *,
    outcome: str,
    duration_seconds: float,
    unassigned: int | None = None,
) -> None:
    labels = {"outcome": (outcome or "unknown")[:64]}
    reg = get_metrics_registry()
    reg.inc(POSITION_RECONCILIATION_TOTAL, "Position reconciliation attempts", labels)
    reg.observe(
        POSITION_RECONCILIATION_DURATION_SECONDS,
        "Position reconciliation duration seconds",
        duration_seconds,
        labels,
    )
    if outcome == "conflict":
        reg.inc(
            POSITION_RECONCILIATION_CONFLICT_TOTAL,
            "Position reconciliation conflicts",
            labels,
        )
    if unassigned is not None and unassigned > 0:
        # Low-cardinality gauge-like counter increment per batch size bucket.
        bucket = "1" if unassigned == 1 else "2_10" if unassigned <= 10 else "11_plus"
        reg.inc(
            POSITION_RECONCILIATION_UNASSIGNED_TOTAL,
            "Unassigned products after reconciliation",
            {**labels, "status": bucket},
        )
