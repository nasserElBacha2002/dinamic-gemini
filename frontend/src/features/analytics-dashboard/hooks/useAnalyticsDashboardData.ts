import { useMemo } from 'react';
import { useAnalyticsDashboard } from '../../analytics/hooks';
import { useObservabilityMetrics } from '../../../hooks/useObservabilityMetrics';
import { useAnalyticsCostSummary } from '../../../hooks/useAnalyticsCostSummary';
import type { AnalyticsDashboardFilterParams } from '../types';

export function useAnalyticsDashboardData(params: AnalyticsDashboardFilterParams, enabled = true) {
  const analytics = useAnalyticsDashboard(params.analytics, enabled);
  const observability = useObservabilityMetrics(params.observability, { enabled });
  const costSummary = useAnalyticsCostSummary(params.costSummary, { enabled });

  const isAnalyticsLoading = analytics.isLoading;
  const isObservabilityLoading = observability.isLoading;
  const isCostSummaryLoading = costSummary.isLoading;
  const isLoading = isAnalyticsLoading || isObservabilityLoading || isCostSummaryLoading;

  const analyticsError = analytics.isError ? analytics.errors[0] ?? null : null;
  const observabilityError = observability.isError ? observability.error : null;
  const costSummaryError = costSummary.isError ? costSummary.error : null;

  const analyticsOk = !analytics.isError && Boolean(analytics.summary);
  const observabilityOk = !observability.isError && Boolean(observability.data?.totals);
  const costSummaryOk = !costSummary.isError && Boolean(costSummary.data?.totals);

  const hasPartialFailure = useMemo(
    () =>
      (analytics.isError && (observabilityOk || costSummaryOk)) ||
      (observability.isError && (analyticsOk || costSummaryOk)) ||
      (costSummary.isError && (analyticsOk || observabilityOk)),
    [
      analytics.isError,
      observability.isError,
      costSummary.isError,
      analyticsOk,
      observabilityOk,
      costSummaryOk,
    ]
  );

  const hasMixedLoadedData = useMemo(
    () =>
      !isAnalyticsLoading &&
      !isObservabilityLoading &&
      !analytics.isError &&
      !observability.isError &&
      ((analyticsOk && !observabilityOk) || (!analyticsOk && observabilityOk)),
    [
      isAnalyticsLoading,
      isObservabilityLoading,
      analytics.isError,
      observability.isError,
      analyticsOk,
      observabilityOk,
    ]
  );

  const refetchAll = () => {
    analytics.refetchAll();
    void observability.refetch();
    void costSummary.refetch();
  };

  return {
    analytics,
    observability,
    costSummary,
    isLoading,
    isAnalyticsLoading,
    isObservabilityLoading,
    isCostSummaryLoading,
    analyticsError,
    observabilityError,
    costSummaryError,
    hasPartialFailure,
    hasMixedLoadedData,
    refetchAll,
  };
}
