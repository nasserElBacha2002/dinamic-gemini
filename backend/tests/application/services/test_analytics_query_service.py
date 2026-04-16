"""AnalyticsQueryService — scope validation (Phase 4 wiring)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.errors import AnalyticsScopeValidationError
from src.application.services.analytics_query_service import (
    AnalyticsQueryService,
    validate_analytics_filters_scope,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository


class _StubAnalyticsRepo:
    """Minimal stub — only scope validation is under test."""

    def get_summary(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def get_trends(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def get_inventory_performance(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def get_aisle_issues(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def get_quality_patterns(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")

    def get_manual_intervention_breakdown(self, filters):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")


def test_validate_analytics_filters_scope_accepts_matching_inventory_and_aisle() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aisles = MemoryAisleRepository()
    aisles.save(Aisle("aisle-1", "inv-1", "A1", AisleStatus.CREATED, now, now))
    f = AnalyticsFilters(
        date_from=None,
        date_to=None,
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    validate_analytics_filters_scope(f, aisles)


def test_validate_analytics_filters_scope_rejects_aisle_not_in_inventory() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aisles = MemoryAisleRepository()
    aisles.save(Aisle("aisle-1", "inv-other", "A1", AisleStatus.CREATED, now, now))
    f = AnalyticsFilters(
        date_from=None,
        date_to=None,
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    with pytest.raises(AnalyticsScopeValidationError, match="does not belong"):
        validate_analytics_filters_scope(f, aisles)


def test_analytics_query_service_validate_scope_delegates() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aisles = MemoryAisleRepository()
    aisles.save(Aisle("aisle-1", "inv-other", "A1", AisleStatus.CREATED, now, now))
    svc = AnalyticsQueryService(_StubAnalyticsRepo(), aisles)
    f = AnalyticsFilters(
        date_from=None,
        date_to=None,
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    with pytest.raises(AnalyticsScopeValidationError):
        svc.validate_scope(f)
