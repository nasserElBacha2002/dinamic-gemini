"""In-process counters for Phase 3 job lease fencing (low-cardinality labels only)."""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, str, str], int] = defaultdict(int)

# Metric names (no job_id labels).
METRIC_ACQUIRE = "job_lease_acquire_total"
METRIC_RENEW = "job_lease_renew_total"
METRIC_LOST = "job_lease_lost_total"
METRIC_STALE_WRITE = "job_stale_write_rejected_total"
METRIC_REACQUIRE = "job_lease_reacquire_total"


def inc_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> None:
    """Increment a lease metric. Labels are limited to ``operation`` and ``outcome``."""
    key = (name, (operation or "default")[:64], (outcome or "ok")[:64])
    with _lock:
        _counters[key] += 1


def get_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> int:
    with _lock:
        return int(_counters.get((name, operation[:64], outcome[:64]), 0))


def reset_lease_metrics_for_tests() -> None:
    with _lock:
        _counters.clear()


def snapshot_lease_metrics() -> dict[str, int]:
    """Flat snapshot ``name|operation|outcome -> count`` for tests/diagnostics."""
    with _lock:
        return {f"{n}|{op}|{out}": v for (n, op, out), v in _counters.items()}
