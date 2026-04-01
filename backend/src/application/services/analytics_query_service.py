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
from src.application.ports.analytics_repository import AnalyticsRepository


class AnalyticsQueryService:
    def __init__(self, repo: AnalyticsRepository) -> None:
        self._repo = repo

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
