"""In-process counters for Phase 3 job lease fencing (low-cardinality labels only).

Phase 5: delegates to the single observability metrics registry.
"""

from __future__ import annotations

from src.observability.metrics.instruments import (
    JOB_LEASE_ACQUIRE_TOTAL,
    JOB_LEASE_LOST_TOTAL,
    JOB_LEASE_REACQUIRE_TOTAL,
    JOB_LEASE_RENEW_TOTAL,
    JOB_STALE_WRITE_REJECTED_TOTAL,
)
from src.observability.metrics.instruments import (
    inc_lease_metric as _inc_registry,
)
from src.observability.metrics.registry import get_metrics_registry

# Metric names (no job_id labels).
METRIC_ACQUIRE = JOB_LEASE_ACQUIRE_TOTAL
METRIC_RENEW = JOB_LEASE_RENEW_TOTAL
METRIC_LOST = JOB_LEASE_LOST_TOTAL
METRIC_STALE_WRITE = JOB_STALE_WRITE_REJECTED_TOTAL
METRIC_REACQUIRE = JOB_LEASE_REACQUIRE_TOTAL


def inc_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> None:
    """Increment a lease metric. Labels are limited to ``operation`` and ``outcome``."""
    _inc_registry(name, operation=operation, outcome=outcome)


def get_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> int:
    reg = get_metrics_registry()
    with reg._lock:  # noqa: SLF001 — test/diagnostic read of process counters
        counter = reg._counters.get(name)
        if counter is None:
            return 0
        from src.observability.metrics.registry import _labels_key, _validate_labels

        key = _labels_key(_validate_labels({"operation": operation, "outcome": outcome}))
        return int(counter.values.get(key, 0))


def reset_lease_metrics_for_tests() -> None:
    get_metrics_registry().reset_for_tests()


def snapshot_lease_metrics() -> dict[str, int]:
    """Flat snapshot ``name|operation|outcome -> count`` for tests/diagnostics."""
    reg = get_metrics_registry()
    out: dict[str, int] = {}
    with reg._lock:  # noqa: SLF001
        for name, counter in reg._counters.items():
            if not name.startswith("job_lease_") and name != METRIC_STALE_WRITE:
                continue
            for labels, value in counter.values.items():
                label_map = dict(labels)
                op = label_map.get("operation", "default")
                outcome = label_map.get("outcome", "ok")
                out[f"{name}|{op}|{outcome}"] = int(value)
    return out
