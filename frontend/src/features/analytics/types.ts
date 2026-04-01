/**
 * Analytics feature types — re-export API DTOs; add UI-only helpers here if needed.
 */

export type {
  AnalyticsSummaryResponse,
  AnalyticsTrendsResponse,
  AnalyticsTrendPoint,
  InventoryPerformanceRow,
  InventoryPerformanceListResponse,
  AisleIssueRow,
  AisleIssueListResponse,
  QualityPatternRow,
  QualityPatternListResponse,
  ManualInterventionCategory,
  ManualInterventionBreakdownResponse,
} from '../../api/types/analytics';

export type { AnalyticsQueryParams } from '../../api/client';
