"""Non-repository services constructed for the v3 composition root (Phase C4)."""

from __future__ import annotations

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, PositionRepository
from src.application.ports.services import MetricsCalculator, WorkerLaunchService


def build_metrics_calculator(
    *,
    aisle_repo: AisleRepository,
    position_repo: PositionRepository,
) -> MetricsCalculator:
    from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService

    return InventoryMetricsService(
        aisle_repo=aisle_repo,
        position_repo=position_repo,
    )


def build_worker_launch_service() -> WorkerLaunchService:
    from src.infrastructure.services.on_demand_worker_launch_service import (
        OnDemandWorkerLaunchService,
    )

    return OnDemandWorkerLaunchService()


def build_clock() -> Clock:
    from src.infrastructure.adapters.clock import UtcClock

    return UtcClock()
