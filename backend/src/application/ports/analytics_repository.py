"""Analytics repository port — aggregates for Phase 5.1."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.application.dto.analytics_dto import (
    AisleIssueRowDTO,
    AnalyticsFilters,
    AnalyticsSummaryDTO,
    AnalyticsTrendsDTO,
    InventoryPerformanceRowDTO,
    ManualInterventionBreakdownDTO,
    QualityPatternRowDTO,
)


class AnalyticsRepository(ABC):
    @abstractmethod
    def get_summary(self, filters: AnalyticsFilters) -> AnalyticsSummaryDTO: ...

    @abstractmethod
    def get_trends(self, filters: AnalyticsFilters) -> AnalyticsTrendsDTO: ...

    @abstractmethod
    def get_inventory_performance(
        self, filters: AnalyticsFilters
    ) -> list[InventoryPerformanceRowDTO]: ...

    @abstractmethod
    def get_aisle_issues(self, filters: AnalyticsFilters) -> list[AisleIssueRowDTO]: ...

    @abstractmethod
    def get_quality_patterns(self, filters: AnalyticsFilters) -> list[QualityPatternRowDTO]: ...

    @abstractmethod
    def get_manual_intervention_breakdown(
        self, filters: AnalyticsFilters
    ) -> ManualInterventionBreakdownDTO: ...
