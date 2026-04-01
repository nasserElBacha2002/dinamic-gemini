/** Feature boundary for analytics HTTP — delegates to shared v3 client. */

export {
  getAnalyticsManualInterventions,
  getAnalyticsSummary,
  getAnalyticsTrends,
  getAnalyticsInventoryPerformance,
  getAnalyticsAisleIssues,
  getAnalyticsQualityPatterns,
  type AnalyticsQueryParams,
} from '../../api/client';
