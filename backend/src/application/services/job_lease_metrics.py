"""In-process counters for Phase 3 job lease fencing (low-cardinality labels only).

Phase 5: delegates to the single observability metrics registry (public APIs only).
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

METRIC_ACQUIRE = JOB_LEASE_ACQUIRE_TOTAL
METRIC_RENEW = JOB_LEASE_RENEW_TOTAL
METRIC_LOST = JOB_LEASE_LOST_TOTAL
METRIC_STALE_WRITE = JOB_STALE_WRITE_REJECTED_TOTAL
METRIC_REACQUIRE = JOB_LEASE_REACQUIRE_TOTAL


def inc_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> None:
    _inc_registry(name, operation=operation, outcome=outcome)


def get_lease_metric(name: str, *, operation: str = "default", outcome: str = "ok") -> int:
    return int(
        get_metrics_registry().get_counter_value(
            name, {"operation": operation, "outcome": outcome}
        )
    )


def reset_lease_metrics_for_tests() -> None:
    get_metrics_registry().reset_for_tests()


def snapshot_lease_metrics() -> dict[str, int]:
    snap = get_metrics_registry().snapshot()
    out: dict[str, int] = {}
    for key, value in snap.items():
        name = key.split("|", 1)[0]
        if name.startswith("job_lease_") or name == METRIC_STALE_WRITE:
            # Convert snapshot key ``name|operation=x|outcome=y`` → ``name|x|y``
            parts = key.split("|")
            if len(parts) == 1:
                out[name] = int(value)
                continue
            op = "default"
            outcome = "ok"
            for part in parts[1:]:
                if part.startswith("operation="):
                    op = part.split("=", 1)[1]
                elif part.startswith("outcome="):
                    outcome = part.split("=", 1)[1]
            out[f"{name}|{op}|{outcome}"] = int(value)
    return out
