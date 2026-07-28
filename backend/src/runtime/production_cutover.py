"""Phase 10 — configurable production cutover / alert thresholds.

Thresholds are env-driven so ops can agree SLOs without code changes.
Defaults are conservative starting points, not hard product SLAs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ProductionCutoverThresholds:
    min_success_rate: float
    max_error_rate: float
    max_duplicate_rate: float
    max_stale_rate: float
    min_recovery_success_rate: float
    queue_depth_warning: int
    queue_depth_critical: int
    oldest_pending_age_warning_sec: int
    oldest_pending_age_critical_sec: int
    max_p95_job_duration_ms: int


def load_production_cutover_thresholds() -> ProductionCutoverThresholds:
    return ProductionCutoverThresholds(
        min_success_rate=_env_float("PRODUCTION_CUTOVER_MIN_SUCCESS_RATE", 0.99),
        max_error_rate=_env_float("PRODUCTION_CUTOVER_MAX_ERROR_RATE", 0.01),
        max_duplicate_rate=_env_float("PRODUCTION_CUTOVER_MAX_DUPLICATE_RATE", 0.0),
        max_stale_rate=_env_float("PRODUCTION_CUTOVER_MAX_STALE_RATE", 0.02),
        min_recovery_success_rate=_env_float(
            "PRODUCTION_CUTOVER_MIN_RECOVERY_SUCCESS_RATE", 0.99
        ),
        queue_depth_warning=_env_int("PRODUCTION_ALERT_QUEUE_DEPTH_WARNING", 100),
        queue_depth_critical=_env_int("PRODUCTION_ALERT_QUEUE_DEPTH_CRITICAL", 500),
        oldest_pending_age_warning_sec=_env_int(
            "PRODUCTION_ALERT_OLDEST_PENDING_WARNING_SEC", 900
        ),
        oldest_pending_age_critical_sec=_env_int(
            "PRODUCTION_ALERT_OLDEST_PENDING_CRITICAL_SEC", 3600
        ),
        max_p95_job_duration_ms=_env_int("PRODUCTION_CUTOVER_MAX_P95_JOB_MS", 0),
    )


RolloutDecision = Literal["continue", "pause_warning", "pause_critical"]


@dataclass(frozen=True, slots=True)
class RolloutPauseSignals:
    success_rate: float
    error_rate: float
    duplicate_rate: float
    stale_rate: float
    recovery_success_rate: float
    queue_depth: int | None = None
    oldest_pending_age_sec: int | None = None
    p95_job_duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RolloutPauseResult:
    decision: RolloutDecision
    reasons: tuple[str, ...]


def evaluate_rollout_pause(
    thresholds: ProductionCutoverThresholds,
    signals: RolloutPauseSignals,
) -> RolloutPauseResult:
    reasons: list[str] = []
    decision: RolloutDecision = "continue"

    def bump(level: RolloutDecision, reason: str) -> None:
        nonlocal decision
        reasons.append(reason)
        if level == "pause_critical":
            decision = "pause_critical"
        elif decision == "continue":
            decision = level

    if signals.success_rate < thresholds.min_success_rate:
        bump(
            "pause_critical",
            f"success_rate {signals.success_rate} < {thresholds.min_success_rate}",
        )
    if signals.error_rate > thresholds.max_error_rate:
        bump(
            "pause_critical",
            f"error_rate {signals.error_rate} > {thresholds.max_error_rate}",
        )
    if signals.duplicate_rate > thresholds.max_duplicate_rate:
        bump(
            "pause_critical",
            f"duplicate_rate {signals.duplicate_rate} > {thresholds.max_duplicate_rate}",
        )
    if signals.stale_rate > thresholds.max_stale_rate:
        bump(
            "pause_warning",
            f"stale_rate {signals.stale_rate} > {thresholds.max_stale_rate}",
        )
    if signals.recovery_success_rate < thresholds.min_recovery_success_rate:
        bump(
            "pause_critical",
            f"recovery_success_rate {signals.recovery_success_rate} < "
            f"{thresholds.min_recovery_success_rate}",
        )
    if signals.queue_depth is not None:
        if signals.queue_depth >= thresholds.queue_depth_critical:
            bump(
                "pause_critical",
                f"queue_depth {signals.queue_depth} >= {thresholds.queue_depth_critical}",
            )
        elif signals.queue_depth >= thresholds.queue_depth_warning:
            bump(
                "pause_warning",
                f"queue_depth {signals.queue_depth} >= {thresholds.queue_depth_warning}",
            )
    if signals.oldest_pending_age_sec is not None:
        if signals.oldest_pending_age_sec >= thresholds.oldest_pending_age_critical_sec:
            bump(
                "pause_critical",
                f"oldest_pending_age_sec {signals.oldest_pending_age_sec} >= "
                f"{thresholds.oldest_pending_age_critical_sec}",
            )
        elif signals.oldest_pending_age_sec >= thresholds.oldest_pending_age_warning_sec:
            bump(
                "pause_warning",
                f"oldest_pending_age_sec {signals.oldest_pending_age_sec} >= "
                f"{thresholds.oldest_pending_age_warning_sec}",
            )
    if (
        thresholds.max_p95_job_duration_ms > 0
        and signals.p95_job_duration_ms is not None
        and signals.p95_job_duration_ms > thresholds.max_p95_job_duration_ms
    ):
        bump(
            "pause_warning",
            f"p95_job_duration_ms {signals.p95_job_duration_ms} > "
            f"{thresholds.max_p95_job_duration_ms}",
        )

    return RolloutPauseResult(decision=decision, reasons=tuple(reasons))
