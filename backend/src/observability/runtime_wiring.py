"""Phase 5 — wire operational metrics collector and recovery scheduler at API startup."""

from __future__ import annotations

import logging
from typing import Any

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.stale_job_recovery_scheduler import StaleJobRecoveryScheduler
from src.application.use_cases.recovery.recover_stale_job import RecoverStaleJobUseCase
from src.config import load_settings, resolve_sqlserver_connection_config
from src.database.sqlserver import SqlServerClient
from src.infrastructure.adapters.clock import UtcClock
from src.infrastructure.observability.memory_operational_metrics_source import (
    MemoryOperationalMetricsSource,
)
from src.infrastructure.observability.sql_operational_metrics_source import (
    SqlOperationalMetricsSource,
)
from src.observability.metrics.registry import MetricsRegistry, get_metrics_registry
from src.observability.operational_metrics import configure_operational_metrics_collector

logger = logging.getLogger(__name__)

_recovery_scheduler: StaleJobRecoveryScheduler | None = None


def configure_metrics_registry_limits(settings: Any | None = None) -> MetricsRegistry:
    settings = settings or load_settings()
    reg = get_metrics_registry()
    max_series = int(getattr(settings, "metrics_max_series_per_metric", 500) or 500)
    reg.configure_max_series(max_series)
    return reg


def wire_operational_metrics_collector(container: Any, settings: Any | None = None) -> None:
    """Configure SQL or memory operational gauges source (fail-soft on scrape)."""
    settings = settings or load_settings()
    source: Any
    try:
        if bool(getattr(settings, "sqlserver_enabled", False)):
            sql_res = resolve_sqlserver_connection_config()
            if sql_res.connection_string.strip():
                source = SqlOperationalMetricsSource(
                    SqlServerClient(sql_res.connection_string.strip())
                )
            else:
                source = MemoryOperationalMetricsSource(container.get_job_repository())
        else:
            source = MemoryOperationalMetricsSource(container.get_job_repository())
    except Exception:
        logger.warning("operational metrics wiring failed; using memory source", exc_info=True)
        try:
            source = MemoryOperationalMetricsSource(container.get_job_repository())
        except Exception:
            source = MemoryOperationalMetricsSource(None)
    configure_operational_metrics_collector(source, ttl_sec=15.0)


def wire_recovery_scheduler(
    container: Any, settings: Any | None = None
) -> StaleJobRecoveryScheduler | None:
    """Start StaleJobRecoveryScheduler when RECOVERY_ENABLED=true."""
    global _recovery_scheduler
    settings = settings or load_settings()
    if _recovery_scheduler is not None:
        _recovery_scheduler.stop(timeout_sec=1.0)
        _recovery_scheduler = None
    if not bool(getattr(settings, "recovery_enabled", False)):
        logger.info("Recovery scheduler disabled (RECOVERY_ENABLED=false)")
        return None

    job_repo = container.get_job_repository()
    aisle_repo = container.get_aisle_repository()
    clock = UtcClock()
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=container.get_worker_launch_service(),
        clock=clock,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=container.get_inventory_repository(),
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    use_case = RecoverStaleJobUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        launch_service=launch,
        clock=clock,
    )
    scheduler = StaleJobRecoveryScheduler(
        use_case=use_case,
        job_repo=job_repo,
        enabled=True,
        interval_sec=int(settings.recovery_interval_sec),
        batch_size=int(settings.recovery_batch_size),
        max_attempts=int(settings.recovery_max_attempts),
        stale_after_seconds=int(settings.worker_stale_running_timeout_sec or 900),
    )
    scheduler.start()
    _recovery_scheduler = scheduler
    return scheduler


def stop_recovery_scheduler() -> None:
    global _recovery_scheduler
    if _recovery_scheduler is not None:
        _recovery_scheduler.stop()
        _recovery_scheduler = None


def refresh_operational_gauges_for_scrape() -> None:
    """Best-effort refresh before /metrics render; never raises."""
    from src.observability.operational_metrics import get_operational_metrics_collector

    collector = get_operational_metrics_collector()
    if collector is None:
        return
    try:
        collector.refresh_if_due()
    except Exception:
        logger.warning("operational gauges refresh failed", exc_info=True)
