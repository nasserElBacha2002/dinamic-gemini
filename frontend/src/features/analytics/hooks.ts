import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { queryKeys } from '../../api/queryKeys';
import {
  getAnalyticsSummary,
  getAnalyticsTrends,
  getAnalyticsInventoryPerformance,
  getAnalyticsAisleIssues,
  getAnalyticsQualityPatterns,
  type AnalyticsQueryParams,
} from './api';

function keyPayload(p: AnalyticsQueryParams): Record<string, string | undefined> {
  return {
    date_from: p.date_from ?? undefined,
    date_to: p.date_to ?? undefined,
    inventory_id: p.inventory_id ?? undefined,
    aisle_id: p.aisle_id ?? undefined,
  };
}

/**
 * Load all analytics endpoints in parallel for the Metrics page.
 */
export function useAnalyticsDashboard(params: AnalyticsQueryParams, enabled = true) {
  const kp = useMemo(() => keyPayload(params), [params]);

  const results = useQueries({
    queries: [
      {
        queryKey: queryKeys.analytics.summary(kp),
        queryFn: () => getAnalyticsSummary(params),
        enabled,
      },
      {
        queryKey: queryKeys.analytics.trends(kp),
        queryFn: () => getAnalyticsTrends(params),
        enabled,
      },
      {
        queryKey: queryKeys.analytics.inventories(kp),
        queryFn: () => getAnalyticsInventoryPerformance(params),
        enabled,
      },
      {
        queryKey: queryKeys.analytics.aisles(kp),
        queryFn: () => getAnalyticsAisleIssues(params),
        enabled,
      },
      {
        queryKey: queryKeys.analytics.quality(kp),
        queryFn: () => getAnalyticsQualityPatterns(params),
        enabled,
      },
    ],
  });

  const [summaryQ, trendsQ, invQ, aisleQ, qualityQ] = results;

  const isLoading = results.some((r) => r.isLoading);
  const isError = results.some((r) => r.isError);
  const errors = results.map((r) => r.error).filter(Boolean);

  const refetchAll = () => {
    void Promise.all(results.map((r) => r.refetch()));
  };

  return {
    summary: summaryQ.data,
    trends: trendsQ.data,
    inventoryPerformance: invQ.data,
    aisleIssues: aisleQ.data,
    quality: qualityQ.data,
    isLoading,
    isError,
    errors,
    refetchAll,
    queries: { summaryQ, trendsQ, invQ, aisleQ, qualityQ },
  };
}
