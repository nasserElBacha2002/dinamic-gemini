"""Phase 10 production cutover / alert catalog tests."""

from __future__ import annotations

from src.runtime.production_alerts import list_production_alerts
from src.runtime.production_cutover import (
    RolloutPauseSignals,
    evaluate_rollout_pause,
    load_production_cutover_thresholds,
)


def test_load_cutover_defaults(monkeypatch):
    monkeypatch.delenv("PRODUCTION_CUTOVER_MIN_SUCCESS_RATE", raising=False)
    t = load_production_cutover_thresholds()
    assert t.min_success_rate == 0.99
    assert t.queue_depth_critical == 500


def test_load_cutover_env_override(monkeypatch):
    monkeypatch.setenv("PRODUCTION_CUTOVER_MIN_SUCCESS_RATE", "0.95")
    monkeypatch.setenv("PRODUCTION_ALERT_QUEUE_DEPTH_WARNING", "10")
    t = load_production_cutover_thresholds()
    assert t.min_success_rate == 0.95
    assert t.queue_depth_warning == 10


def test_evaluate_rollout_pause_critical():
    t = load_production_cutover_thresholds()
    result = evaluate_rollout_pause(
        t,
        RolloutPauseSignals(
            success_rate=0.5,
            error_rate=0.0,
            duplicate_rate=0.0,
            stale_rate=0.0,
            recovery_success_rate=1.0,
        ),
    )
    assert result.decision == "pause_critical"
    assert result.reasons


def test_evaluate_rollout_pause_queue_warning(monkeypatch):
    monkeypatch.setenv("PRODUCTION_ALERT_QUEUE_DEPTH_WARNING", "50")
    monkeypatch.setenv("PRODUCTION_ALERT_QUEUE_DEPTH_CRITICAL", "200")
    t = load_production_cutover_thresholds()
    result = evaluate_rollout_pause(
        t,
        RolloutPauseSignals(
            success_rate=1.0,
            error_rate=0.0,
            duplicate_rate=0.0,
            stale_rate=0.0,
            recovery_success_rate=1.0,
            queue_depth=75,
        ),
    )
    assert result.decision == "pause_warning"


def test_alert_catalog_non_empty():
    all_alerts = list_production_alerts()
    assert len(all_alerts) >= 8
    critical = list_production_alerts(severity="critical")
    assert all(a.severity == "critical" for a in critical)
    assert all(a.owner and a.action for a in all_alerts)
