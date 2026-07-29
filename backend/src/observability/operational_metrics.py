"""Phase 5 — SQL-backed operational gauges with short TTL cache."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from src.domain.jobs.entities import JobStatus
from src.observability.metrics.instruments import (
    ARTIFACT_OUTBOX_FAILED,
    ARTIFACT_OUTBOX_PENDING,
    JOB_ACTIVE_LEASES,
    JOB_EXPIRED_RUNNING_LEASES,
    JOBS_IN_STATE,
)
from src.observability.metrics.registry import get_metrics_registry

logger = logging.getLogger(__name__)

COLLECTOR_ERROR_METRIC = "operational_metrics_collector_errors_total"
DEFAULT_TTL_SEC = 15.0

_ALLOWED_JOB_STATUSES = frozenset(s.value for s in JobStatus)


class OperationalMetricsSource(Protocol):
    def count_jobs_by_status(self) -> dict[str, int]: ...

    def count_active_leases(self) -> int: ...

    def count_expired_running_leases(self) -> int: ...

    def count_artifact_outbox(self) -> tuple[int, int]:
        """Return (pending, failed)."""
        ...


@dataclass
class _Cache:
    expires_at: float = 0.0
    ok: bool = False


class OperationalMetricsCollector:
    """Refresh operational gauges from aggregated SQL (or memory) queries."""

    def __init__(
        self,
        source: OperationalMetricsSource,
        *,
        ttl_sec: float = DEFAULT_TTL_SEC,
    ) -> None:
        self._source = source
        self._ttl = max(1.0, float(ttl_sec))
        self._lock = threading.Lock()
        self._inflight = False
        self._cache = _Cache()

    def refresh_if_due(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        with self._lock:
            if not force and self._cache.ok and now < self._cache.expires_at:
                return True
            if self._inflight:
                return self._cache.ok
            self._inflight = True
        try:
            by_status = self._source.count_jobs_by_status()
            active = self._source.count_active_leases()
            expired = self._source.count_expired_running_leases()
            pending, failed = self._source.count_artifact_outbox()
            reg = get_metrics_registry()
            for status, count in by_status.items():
                status_key = str(status).strip().lower()
                if status_key not in _ALLOWED_JOB_STATUSES:
                    status_key = "unknown"
                reg.set_gauge(
                    JOBS_IN_STATE,
                    "Jobs currently in status",
                    float(count),
                    {"status": status_key, "job_type": "process_aisle"},
                )
            reg.set_gauge(JOB_ACTIVE_LEASES, "Active unexpired job leases", float(active), {})
            reg.set_gauge(
                JOB_EXPIRED_RUNNING_LEASES,
                "RUNNING jobs with expired leases",
                float(expired),
                {},
            )
            reg.set_gauge(
                ARTIFACT_OUTBOX_PENDING,
                "Artifact outbox pending rows",
                float(pending),
                {},
            )
            reg.set_gauge(
                ARTIFACT_OUTBOX_FAILED,
                "Artifact outbox failed rows",
                float(failed),
                {},
            )
            with self._lock:
                self._cache = _Cache(expires_at=time.monotonic() + self._ttl, ok=True)
            return True
        except Exception as exc:
            logger.warning(
                "operational_metrics_collector_failed error=%s",
                type(exc).__name__,
            )
            get_metrics_registry().inc(
                COLLECTOR_ERROR_METRIC,
                "Operational metrics collector failures",
                {"reason_code": type(exc).__name__[:64]},
            )
            with self._lock:
                # Keep last success; mark not ok for retry soon
                self._cache = _Cache(expires_at=time.monotonic() + min(5.0, self._ttl), ok=False)
            return False
        finally:
            with self._lock:
                self._inflight = False


_collector: OperationalMetricsCollector | None = None
_collector_lock = threading.Lock()


def get_operational_metrics_collector() -> OperationalMetricsCollector | None:
    return _collector


def configure_operational_metrics_collector(
    source: OperationalMetricsSource,
    *,
    ttl_sec: float = DEFAULT_TTL_SEC,
) -> OperationalMetricsCollector:
    global _collector
    with _collector_lock:
        _collector = OperationalMetricsCollector(source, ttl_sec=ttl_sec)
        return _collector
