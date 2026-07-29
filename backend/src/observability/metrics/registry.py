"""Phase 5 — single in-process metrics registry (Prometheus text exposition).

No high-cardinality labels (no job_id / aisle_id / inventory_id / execution_id / owner_id).
Observability failures must not break business flows.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

_ALLOWED_LABEL_KEYS = frozenset(
    {
        "component",
        "operation",
        "outcome",
        "status",
        "job_type",
        "provider",
        "stage",
        "reason_code",
        "environment",
        "repository_backend",
        "method",
        "route_template",
        "status_class",
        "reason",
        "artifact_kind",
        "storage_backend",
        "worker_role",
        "host_group",
        "error_class",
        "failure_code",
    }
)

_FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "job_id",
        "aisle_id",
        "inventory_id",
        "execution_id",
        "owner_id",
        "claim_owner_id",
        "client_id",
        "path",
        "url",
        "filename",
        "storage_key",
    }
)


class MetricsError(ValueError):
    """Invalid metric label / name."""


def _validate_labels(labels: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in labels.items():
        k = (key or "").strip()
        if not k:
            continue
        if k in _FORBIDDEN_LABEL_KEYS or k.endswith("_id"):
            raise MetricsError(f"high-cardinality / forbidden label rejected: {k}")
        if k not in _ALLOWED_LABEL_KEYS:
            # Strict allowlist to keep cardinality under control.
            raise MetricsError(f"label not in allowlist: {k}")
        v = str(value if value is not None else "")[:64] or "unknown"
        out[k] = v
    return out


def _labels_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


@dataclass
class _Counter:
    name: str
    help: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)

    def inc(self, labels: dict[str, str], amount: float = 1.0) -> None:
        key = _labels_key(_validate_labels(labels))
        self.values[key] = self.values.get(key, 0.0) + amount


@dataclass
class _Gauge:
    name: str
    help: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)

    def set(self, labels: dict[str, str], value: float) -> None:
        key = _labels_key(_validate_labels(labels))
        self.values[key] = float(value)

    def inc(self, labels: dict[str, str], amount: float = 1.0) -> None:
        key = _labels_key(_validate_labels(labels))
        self.values[key] = self.values.get(key, 0.0) + amount

    def dec(self, labels: dict[str, str], amount: float = 1.0) -> None:
        self.inc(labels, -amount)


_HIST_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)


@dataclass
class _Histogram:
    name: str
    help: str
    buckets: tuple[float, ...] = _HIST_BUCKETS
    # key -> (bucket_counts..., sum, count)
    values: dict[tuple[tuple[str, str], ...], list[float]] = field(default_factory=dict)

    def observe(self, labels: dict[str, str], value: float) -> None:
        key = _labels_key(_validate_labels(labels))
        n = len(self.buckets)
        row = self.values.get(key)
        if row is None:
            row = [0.0] * (n + 2)  # buckets + sum + count
            self.values[key] = row
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                row[i] += 1.0
        row[n] += float(value)
        row[n + 1] += 1.0


class MetricsRegistry:
    """Process-local registry. Counters reset on restart (Prometheus handles restarts)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}

    def _get_counter(self, name: str, help: str) -> _Counter:
        c = self._counters.get(name)
        if c is None:
            c = _Counter(name=name, help=help)
            self._counters[name] = c
        return c

    def _get_gauge(self, name: str, help: str) -> _Gauge:
        g = self._gauges.get(name)
        if g is None:
            g = _Gauge(name=name, help=help)
            self._gauges[name] = g
        return g

    def _get_histogram(self, name: str, help: str) -> _Histogram:
        h = self._histograms.get(name)
        if h is None:
            h = _Histogram(name=name, help=help)
            self._histograms[name] = h
        return h

    def counter(self, name: str, help: str) -> _Counter:
        with self._lock:
            return self._get_counter(name, help)

    def gauge(self, name: str, help: str) -> _Gauge:
        with self._lock:
            return self._get_gauge(name, help)

    def histogram(self, name: str, help: str) -> _Histogram:
        with self._lock:
            return self._get_histogram(name, help)

    def inc(self, name: str, help: str, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        try:
            with self._lock:
                self._get_counter(name, help).inc(labels or {}, amount)
        except MetricsError as exc:
            _log.warning("metrics_inc_rejected name=%s error=%s", name, exc)
        except Exception as exc:  # noqa: BLE001 — never break business flow
            _log.warning("metrics_inc_failed name=%s error=%s", name, type(exc).__name__)

    def set_gauge(self, name: str, help: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            with self._lock:
                self._get_gauge(name, help).set(labels or {}, value)
        except MetricsError as exc:
            _log.warning("metrics_gauge_rejected name=%s error=%s", name, exc)
        except Exception as exc:  # noqa: BLE001
            _log.warning("metrics_gauge_failed name=%s error=%s", name, type(exc).__name__)

    def inc_gauge(
        self,
        name: str,
        help: str,
        labels: dict[str, str] | None = None,
        amount: float = 1.0,
    ) -> None:
        try:
            with self._lock:
                self._get_gauge(name, help).inc(labels or {}, amount)
        except MetricsError as exc:
            _log.warning("metrics_inc_gauge_rejected name=%s error=%s", name, exc)
        except Exception as exc:  # noqa: BLE001
            _log.warning("metrics_inc_gauge_failed name=%s error=%s", name, type(exc).__name__)

    def observe(self, name: str, help: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            with self._lock:
                self._get_histogram(name, help).observe(labels or {}, value)
        except MetricsError as exc:
            _log.warning("metrics_observe_rejected name=%s error=%s", name, exc)
        except Exception as exc:  # noqa: BLE001
            _log.warning("metrics_observe_failed name=%s error=%s", name, type(exc).__name__)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for c in sorted(self._counters.values(), key=lambda x: x.name):
                lines.append(f"# HELP {c.name} {c.help}")
                lines.append(f"# TYPE {c.name} counter")
                for labels, value in sorted(c.values.items()):
                    lines.append(f"{c.name}{_fmt_labels(labels)} {value}")
            for g in sorted(self._gauges.values(), key=lambda x: x.name):
                lines.append(f"# HELP {g.name} {g.help}")
                lines.append(f"# TYPE {g.name} gauge")
                for labels, value in sorted(g.values.items()):
                    lines.append(f"{g.name}{_fmt_labels(labels)} {value}")
            for h in sorted(self._histograms.values(), key=lambda x: x.name):
                lines.append(f"# HELP {h.name} {h.help}")
                lines.append(f"# TYPE {h.name} histogram")
                for labels, row in sorted(h.values.items()):
                    n = len(h.buckets)
                    cumulative = 0.0
                    for i, bound in enumerate(h.buckets):
                        cumulative += row[i]
                        bl = dict(labels)
                        bl_list = list(bl.items()) + [("le", _fmt_le(bound))]
                        lines.append(
                            f"{h.name}_bucket{_fmt_labels(tuple(sorted(bl_list)))} {cumulative}"
                        )
                    bl_inf = list(dict(labels).items()) + [("le", "+Inf")]
                    lines.append(
                        f"{h.name}_bucket{_fmt_labels(tuple(sorted(bl_inf)))} {row[n + 1]}"
                    )
                    lines.append(f"{h.name}_sum{_fmt_labels(labels)} {row[n]}")
                    lines.append(f"{h.name}_count{_fmt_labels(labels)} {row[n + 1]}")
        lines.append("")
        return "\n".join(lines)


def _fmt_le(bound: float) -> str:
    if bound == int(bound):
        return str(int(bound))
    return str(bound)


def _fmt_labels(labels: Iterable[tuple[str, str]]) -> str:
    items = list(labels)
    if not items:
        return ""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in items)
    return "{" + inner + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


_REGISTRY = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    return _REGISTRY


def timed() -> float:
    return time.perf_counter()
