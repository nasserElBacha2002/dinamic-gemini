"""Phase 5 corrections — Prometheus registry golden / cardinality / API tests."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from src.observability.metrics.registry import (
    MetricsRegistry,
    get_metrics_registry,
)
from src.observability.middleware import ObservabilityMiddleware


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    get_metrics_registry().reset_for_tests()
    yield
    get_metrics_registry().reset_for_tests()


def test_histogram_prometheus_golden_output() -> None:
    reg = MetricsRegistry(max_series_per_metric=50)
    reg.observe(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        0.04,
        {"method": "GET", "route_template": "/health", "status_class": "2xx"},
    )
    reg.observe(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        1.5,
        {"method": "GET", "route_template": "/health", "status_class": "2xx"},
    )
    text = reg.render_prometheus()
    assert "# TYPE http_request_duration_seconds histogram" in text
    # Cumulative buckets must be non-decreasing; +Inf == count
    buckets = []
    for line in text.splitlines():
        if line.startswith("http_request_duration_seconds_bucket{"):
            le = re.search(r'le="([^"]+)"', line)
            val = float(line.rsplit(" ", 1)[-1])
            assert le is not None
            buckets.append((le.group(1), val))
    assert buckets, "expected histogram buckets"
    prev = -1.0
    for le, val in buckets:
        assert val >= prev
        prev = val
    count_line = [ln for ln in text.splitlines() if ln.startswith("http_request_duration_seconds_count{")]
    assert len(count_line) == 1
    count = float(count_line[0].rsplit(" ", 1)[-1])
    inf = [v for le, v in buckets if le == "+Inf"][0]
    assert inf == count == 2.0
    sum_line = [ln for ln in text.splitlines() if ln.startswith("http_request_duration_seconds_sum{")]
    assert abs(float(sum_line[0].rsplit(" ", 1)[-1]) - 1.54) < 1e-9


def test_series_limit_rejects_without_evicting() -> None:
    reg = MetricsRegistry(max_series_per_metric=3)
    for i in range(3):
        reg.inc("demo_total", "demo", {"outcome": f"o{i}"})
    before = reg.get_counter_value("demo_total", {"outcome": "o0"})
    reg.inc("demo_total", "demo", {"outcome": "o3"})
    assert reg.get_counter_value("demo_total", {"outcome": "o0"}) == before
    assert reg.series_count("demo_total") == 3
    assert reg.get_counter_value("observability_series_rejected_total", {"reason_code": "demo_total"}) >= 1


def test_type_conflict_and_public_apis() -> None:
    reg = MetricsRegistry()
    reg.inc("x_total", "help", {})
    # Soft-fail: conflicting gauge must not wipe counter series.
    reg.set_gauge("x_total", "help", 1.0, {})
    assert reg.get_counter_value("x_total", {}) == 1.0
    snap = reg.snapshot()
    assert any(k.startswith("x_total") for k in snap)
    assert reg.series_count() >= 1


def test_help_escaping() -> None:
    reg = MetricsRegistry()
    reg.inc('esc_total', 'help with "quotes" and \\ slash', {})
    text = reg.render_prometheus()
    assert 'help with \\"quotes\\" and \\\\ slash' in text


def test_unmatched_route_template() -> None:
    app = FastAPI()

    @app.get("/known")
    def known() -> dict[str, str]:
        return {"ok": "1"}

    app.add_middleware(ObservabilityMiddleware, metrics_enabled=True)
    client = TestClient(app)
    client.get("/known")
    client.get("/does-not-exist-abc")
    client.get("/another-missing-xyz")
    text = get_metrics_registry().render_prometheus()
    assert '__unmatched__' in text
    assert "/does-not-exist-abc" not in text


def test_cardinality_storm_unmatched_paths() -> None:
    app = FastAPI()

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"ok": "1"}

    app.add_middleware(ObservabilityMiddleware, metrics_enabled=True)
    client = TestClient(app)
    get_metrics_registry().configure_max_series(20)
    for i in range(200):
        client.get(f"/storm/{i}")
    # All unmatched collapse to one template series (plus method/status variants limited)
    assert get_metrics_registry().series_count("http_requests_total") < 50
    text = get_metrics_registry().render_prometheus()
    assert "/storm/" not in text


def test_streaming_and_exception_metrics() -> None:
    app = FastAPI()

    @app.get("/stream")
    def stream() -> StreamingResponse:
        def gen():
            yield b"a"
            yield b"b"

        return StreamingResponse(gen(), media_type="text/plain")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    app.add_middleware(ObservabilityMiddleware, metrics_enabled=True)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/stream")
    assert r.status_code == 200
    b = client.get("/boom")
    assert b.status_code == 500
    text = get_metrics_registry().render_prometheus()
    assert "http_requests_total" in text


def test_concurrent_observes() -> None:
    reg = get_metrics_registry()

    def work(_: int) -> None:
        reg.inc("conc_total", "c", {"outcome": "ok"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(100)))
    assert reg.get_counter_value("conc_total", {"outcome": "ok"}) == 100.0
