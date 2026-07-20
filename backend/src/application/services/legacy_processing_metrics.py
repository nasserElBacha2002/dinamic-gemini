"""Multi-replica-safe legacy retirement metrics (structured logs + optional counters).

Semantics
---------
* ProcessingEvent / in-process counters are **not** the source of truth across replicas.
* Every increment emits a structured log line with ``metric.name`` / ``metric.value`` so
  log aggregators (or a future Prometheus exporter) can sum by labels.
* Residual LEGACY job creates (historical retry only) are also countable via SQL on
  ``jobs.identification_mode`` / ``execution_strategy`` — see
  ``backend/docs/sql/legacy_processing_usage_report.sql``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_local_totals: dict[str, int] = {
    "legacy_mode_jobs_blocked_total": 0,
    "legacy_mode_config_writes_blocked_total": 0,
    "legacy_mode_jobs_created_residual_total": 0,
    "processing_event_publish_failed_total": 0,
}


def _emit(
    name: str,
    *,
    labels: dict[str, Any] | None = None,
) -> None:
    with _lock:
        _local_totals[name] = int(_local_totals.get(name, 0)) + 1
        total = _local_totals[name]
    parts = [f"metric.name={name}", "metric.value=1", f"metric.local_total={total}"]
    for key, value in (labels or {}).items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


def record_legacy_job_blocked(
    *,
    requested_mode: str | None,
    effective_mode: str,
    resolution_source: str,
) -> None:
    _emit(
        "legacy_mode_jobs_blocked_total",
        labels={
            "requested_mode": requested_mode or "null",
            "effective_mode": effective_mode,
            "resolution_source": resolution_source,
        },
    )


def record_legacy_config_write_blocked(*, context: str, mode: str) -> None:
    _emit(
        "legacy_mode_config_writes_blocked_total",
        labels={"context": context, "mode": mode},
    )


def record_legacy_job_created_residual(
    *,
    effective_mode: str,
    resolution_source: str,
    path: str,
) -> None:
    """Historical retry / residual path that still materializes a LEGACY job row."""
    _emit(
        "legacy_mode_jobs_created_residual_total",
        labels={
            "effective_mode": effective_mode,
            "resolution_source": resolution_source,
            "path": path,
        },
    )


def record_processing_event_publish_failed(*, event_type: str, err_type: str) -> None:
    _emit(
        "processing_event_publish_failed_total",
        labels={"event_type": event_type, "err_type": err_type},
    )


def local_metrics_snapshot() -> dict[str, int]:
    """Process-local totals (debug only — not multi-replica authoritative)."""
    with _lock:
        return dict(_local_totals)


def reset_local_metrics_for_tests() -> None:
    with _lock:
        for key in _local_totals:
            _local_totals[key] = 0


__all__ = [
    "local_metrics_snapshot",
    "record_legacy_config_write_blocked",
    "record_legacy_job_blocked",
    "record_legacy_job_created_residual",
    "record_processing_event_publish_failed",
    "reset_local_metrics_for_tests",
]
