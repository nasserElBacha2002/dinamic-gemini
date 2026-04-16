"""Application service for analytics reads — Phase 5.1."""

from __future__ import annotations

from typing import List

from src.application.dto.analytics_dto import (
    AnalyticsFilters,
    AnalyticsSummaryDTO,
    AnalyticsTrendsDTO,
    AisleIssueRowDTO,
    InventoryPerformanceRowDTO,
    ManualInterventionBreakdownDTO,
    QualityPatternRowDTO,
)
from src.application.errors import AnalyticsScopeValidationError
from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.repositories import AisleRepository


def validate_analytics_filters_scope(filters: AnalyticsFilters, aisle_repo: AisleRepository) -> None:
    """Ensure ``aisle_id`` belongs to ``inventory_id`` when both are set (422 semantics at HTTP boundary)."""
    if filters.aisle_id and filters.inventory_id:
        aisle = aisle_repo.get_by_id(filters.aisle_id)
        if aisle is None or aisle.inventory_id != filters.inventory_id:
            raise AnalyticsScopeValidationError(
                "aisle_id does not belong to the given inventory_id"
            )


class AnalyticsQueryService:
    def __init__(self, repo: AnalyticsRepository, aisle_repo: AisleRepository) -> None:
        self._repo = repo
        self._aisle_repo = aisle_repo

    def validate_scope(self, filters: AnalyticsFilters) -> None:
        validate_analytics_filters_scope(filters, self._aisle_repo)

    def summary(self, filters: AnalyticsFilters) -> AnalyticsSummaryDTO:
        return self._repo.get_summary(filters)

    def trends(self, filters: AnalyticsFilters) -> AnalyticsTrendsDTO:
        return self._repo.get_trends(filters)

    def inventory_performance(self, filters: AnalyticsFilters) -> List[InventoryPerformanceRowDTO]:
        return self._repo.get_inventory_performance(filters)

    def aisle_issues(self, filters: AnalyticsFilters) -> List[AisleIssueRowDTO]:
        return self._repo.get_aisle_issues(filters)

    def quality_patterns(self, filters: AnalyticsFilters) -> List[QualityPatternRowDTO]:
        return self._repo.get_quality_patterns(filters)

    def manual_intervention_breakdown(
        self, filters: AnalyticsFilters
    ) -> ManualInterventionBreakdownDTO:
        return self._repo.get_manual_intervention_breakdown(filters)
