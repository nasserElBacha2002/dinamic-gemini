"""Promotion service builders for Phase 2 Part 3 tests."""

from __future__ import annotations

from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
    MemoryOperationalJobPromotionRepository,
)
from tests.support.worker_phase1.executor_harness import ExecutorHarness


def build_operational_promotion_service(
    harness: ExecutorHarness,
) -> OperationalResultPromotionService:
    promotion_repo = MemoryOperationalJobPromotionRepository(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
    )
    return OperationalResultPromotionService(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        promotion_repo=promotion_repo,
    )
