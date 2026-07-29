"""Phase 5 corrections — single in-process metrics registry (Prometheus text)."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

_log = logging.getLogger(__name__)

MetricKind = Literal["counter", "gauge", "histogram"]

_METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")

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

# HTTP method / status_class allowlists (no arbitrary external strings).
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
_ALLOWED_STATUS_CLASS = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx"})

DEFAULT_MAX_SERIES_PER_METRIC = 500
SERIES_REJECTED_METRIC = "observability_series_rejected_total"

_HIST_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)

_last_reject_log_mono = 0.0


class MetricsError(ValueError):
    """Invalid metric name / label / type conflict."""


def _validate_metric_name(name: str) -> str:
    n = (name or "").strip()
    if not n or not _METRIC_NAME_RE.match(n):
        raise MetricsError(f"invalid metric name: {name!r}")
    return n


def _normalize_label_value(key: str, value: str) -> str:
    v = (value or "").strip()[:64] or "unknown"
    if key == "method":
        u = v.upper()
        return u if u in _ALLOWED_METHODS else "OTHER"
    if key == "status_class":
        return v if v in _ALLOWED_STATUS_CLASS else "5xx"
    if key == "route_template":
        if v in {"__unmatched__", "in_flight"}:
            return v
        if v.startswith("/") and all(c.isalnum() or c in "/_{}-." for c in v):
            return v
        return "__unmatched__"
    return v


def _validate_labels(labels: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in labels.items():
        k = (key or "").strip()
        if not k:
            continue
        if k in _FORBIDDEN_LABEL_KEYS or k.endswith("_id"):
            raise MetricsError(f"high-cardinality / forbidden label rejected: {k}")
        if k not in _ALLOWED_LABEL_KEYS:
            raise MetricsError(f"label not in allowlist: {k}")
        out[k] = _normalize_label_value(k, str(value if value is not None else ""))
    return out


def _labels_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def _escape_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


@dataclass
class _Counter:
    name: str
    help: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass
class _Gauge:
    name: str
    help: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass
class _Histogram:
    name: str
    help: str
    buckets: tuple[float, ...] = _HIST_BUCKETS
    # Non-cumulative bucket counts + sum + count
    values: dict[tuple[tuple[str, str], ...], list[float]] = field(default_factory=dict)


class MetricsRegistry:
    """Process-local registry. Counters reset on restart (Prometheus handles restarts)."""

    def __init__(self, *, max_series_per_metric: int = DEFAULT_MAX_SERIES_PER_METRIC) -> None:
        self._lock = threading.RLock()
        self._max_series = max(1, int(max_series_per_metric))
        self._kinds: dict[str, MetricKind] = {}
        self._helps: dict[str, str] = {}
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}

    def configure_max_series(self, max_series_per_metric: int) -> None:
        with self._lock:
            self._max_series = max(1, int(max_series_per_metric))

    def _ensure_kind(self, name: str, kind: MetricKind, help: str) -> None:
        name = _validate_metric_name(name)
        existing = self._kinds.get(name)
        if existing is not None and existing != kind:
            raise MetricsError(f"metric type conflict for {name}: {existing} vs {kind}")
        prev_help = self._helps.get(name)
        if prev_help is not None and prev_help != help:
            raise MetricsError(f"metric HELP conflict for {name}")
        self._kinds[name] = kind
        self._helps[name] = help

    def _reject_series(self, metric: str) -> None:
        global _last_reject_log_mono
        key: tuple[tuple[str, str], ...] = (("reason_code", metric[:64]),)
        c = self._counters.get(SERIES_REJECTED_METRIC)
        if c is None:
            self._ensure_kind(SERIES_REJECTED_METRIC, "counter", "Series rejected due to cardinality limit")
            c = _Counter(name=SERIES_REJECTED_METRIC, help="Series rejected due to cardinality limit")
            self._counters[SERIES_REJECTED_METRIC] = c
        c.values[key] = c.values.get(key, 0.0) + 1.0
        now = time.monotonic()
        if now - _last_reject_log_mono >= 5.0:
            _last_reject_log_mono = now
            _log.warning("observability_series_rejected metric=%s limit=%s", metric, self._max_series)

    def _can_add_series(self, metric: str, store_len: int, key: tuple[tuple[str, str], ...], existing: dict) -> bool:
        if key in existing:
            return True
        if store_len >= self._max_series:
            self._reject_series(metric)
            return False
        return True

    def _get_counter(self, name: str, help: str) -> _Counter:
        self._ensure_kind(name, "counter", help)
        c = self._counters.get(name)
        if c is None:
            c = _Counter(name=name, help=help)
            self._counters[name] = c
        return c

    def _get_gauge(self, name: str, help: str) -> _Gauge:
        self._ensure_kind(name, "gauge", help)
        g = self._gauges.get(name)
        if g is None:
            g = _Gauge(name=name, help=help)
            self._gauges[name] = g
        return g

    def _get_histogram(self, name: str, help: str) -> _Histogram:
        self._ensure_kind(name, "histogram", help)
        h = self._histograms.get(name)
        if h is None:
            h = _Histogram(name=name, help=help)
            self._histograms[name] = h
        return h

    def inc(self, name: str, help: str, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        try:
            with self._lock:
                c = self._get_counter(name, help)
                key = _labels_key(_validate_labels(labels or {}))
                if not self._can_add_series(name, len(c.values), key, c.values):
                    return
                c.values[key] = c.values.get(key, 0.0) + amount
        except MetricsError as exc:
            _log.warning("metrics_inc_rejected name=%s error=%s", name, exc)

    def set_gauge(self, name: str, help: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            with self._lock:
                g = self._get_gauge(name, help)
                key = _labels_key(_validate_labels(labels or {}))
                if not self._can_add_series(name, len(g.values), key, g.values):
                    return
                g.values[key] = float(value)
        except MetricsError as exc:
            _log.warning("metrics_gauge_rejected name=%s error=%s", name, exc)

    def inc_gauge(
        self,
        name: str,
        help: str,
        labels: dict[str, str] | None = None,
        amount: float = 1.0,
    ) -> None:
        try:
            with self._lock:
                g = self._get_gauge(name, help)
                key = _labels_key(_validate_labels(labels or {}))
                if not self._can_add_series(name, len(g.values), key, g.values):
                    return
                g.values[key] = g.values.get(key, 0.0) + amount
        except MetricsError as exc:
            _log.warning("metrics_inc_gauge_rejected name=%s error=%s", name, exc)

    def observe(self, name: str, help: str, value: float, labels: dict[str, str] | None = None) -> None:
        try:
            with self._lock:
                h = self._get_histogram(name, help)
                key = _labels_key(_validate_labels(labels or {}))
                if not self._can_add_series(name, len(h.values), key, h.values):
                    return
                n = len(h.buckets)
                row = h.values.get(key)
                if row is None:
                    row = [0.0] * (n + 2)
                    h.values[key] = row
                # Non-cumulative: increment only the first matching bucket (or +Inf via count).
                placed = False
                for i, bound in enumerate(h.buckets):
                    if value <= bound:
                        row[i] += 1.0
                        placed = True
                        break
                if not placed:
                    # Counts toward +Inf only (no finite bucket).
                    pass
                row[n] += float(value)
                row[n + 1] += 1.0
        except MetricsError as exc:
            _log.warning("metrics_observe_rejected name=%s error=%s", name, exc)

    def get_counter_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                return 0.0
            key = _labels_key(_validate_labels(labels or {}))
            return float(c.values.get(key, 0.0))

    def series_count(self, name: str | None = None) -> int:
        with self._lock:
            if name is None:
                total = 0
                for c in self._counters.values():
                    total += len(c.values)
                for g in self._gauges.values():
                    total += len(g.values)
                for h in self._histograms.values():
                    total += len(h.values)
                return total
            if name in self._counters:
                return len(self._counters[name].values)
            if name in self._gauges:
                return len(self._gauges[name].values)
            if name in self._histograms:
                return len(self._histograms[name].values)
            return 0

    def snapshot(self) -> dict[str, float]:
        """Flat snapshot ``name|k=v|... -> value`` (counters/gauges only)."""
        out: dict[str, float] = {}
        with self._lock:
            for c in self._counters.values():
                for labels, value in c.values.items():
                    suffix = "|".join(f"{k}={v}" for k, v in labels)
                    out[f"{c.name}|{suffix}" if suffix else c.name] = float(value)
            for g in self._gauges.values():
                for labels, value in g.values.items():
                    suffix = "|".join(f"{k}={v}" for k, v in labels)
                    out[f"{g.name}|{suffix}" if suffix else g.name] = float(value)
        return out

    def reset_for_tests(self) -> None:
        with self._lock:
            self._kinds.clear()
            self._helps.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for c in sorted(self._counters.values(), key=lambda x: x.name):
                lines.append(f'# HELP {c.name} {_escape_help(c.help)}')
                lines.append(f"# TYPE {c.name} counter")
                for labels, value in sorted(c.values.items()):
                    lines.append(f"{c.name}{_fmt_labels(labels)} {value}")
            for g in sorted(self._gauges.values(), key=lambda x: x.name):
                lines.append(f'# HELP {g.name} {_escape_help(g.help)}')
                lines.append(f"# TYPE {g.name} gauge")
                for labels, value in sorted(g.values.items()):
                    lines.append(f"{g.name}{_fmt_labels(labels)} {value}")
            for h in sorted(self._histograms.values(), key=lambda x: x.name):
                lines.append(f'# HELP {h.name} {_escape_help(h.help)}')
                lines.append(f"# TYPE {h.name} histogram")
                for labels, row in sorted(h.values.items()):
                    n = len(h.buckets)
                    cumulative = 0.0
                    for i, bound in enumerate(h.buckets):
                        cumulative += row[i]
                        bl_list = list(dict(labels).items()) + [("le", _fmt_le(bound))]
                        lines.append(
                            f"{h.name}_bucket{_fmt_labels(tuple(sorted(bl_list)))} {cumulative}"
                        )
                    # +Inf must equal count
                    count = row[n + 1]
                    bl_inf = list(dict(labels).items()) + [("le", "+Inf")]
                    lines.append(
                        f"{h.name}_bucket{_fmt_labels(tuple(sorted(bl_inf)))} {count}"
                    )
                    lines.append(f"{h.name}_sum{_fmt_labels(labels)} {row[n]}")
                    lines.append(f"{h.name}_count{_fmt_labels(labels)} {count}")
        lines.append("")
        return "\n".join(lines)


def _fmt_le(bound: float) -> str:
    if bound == int(bound):
        return str(int(bound))
    return repr(float(bound)) if bound < 1 else str(bound)


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
