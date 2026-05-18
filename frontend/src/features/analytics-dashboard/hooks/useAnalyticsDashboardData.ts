import { useMemo } from 'react';
import { useAnalyticsDashboard } from '../../analytics/hooks';
import { useObservabilityMetrics } from '../../../hooks/useObservabilityMetrics';
import type { AnalyticsDashboardFilterParams } from '../types';

export function useAnalyticsDashboardData(params: AnalyticsDashboardFilterParams, enabled = true) {
  const analytics = useAnalyticsDashboard(params.analytics, enabled);
  const observability = useObservabilityMetrics(params.observability, { enabled });

  const isAnalyticsLoading = analytics.isLoading;
  const isObservabilityLoading = observability.isLoading;
  const isLoading = isAnalyticsLoading || isObservabilityLoading;

  const analyticsError = analytics.isError ? analytics.errors[0] ?? null : null;
  const observabilityError = observability.isError ? observability.error : null;

  const analyticsOk = !analytics.isError && Boolean(analytics.summary);
  const observabilityOk = !observability.isError && Boolean(observability.data?.totals);

  const hasPartialFailure = useMemo(
    () => (analytics.isError && observabilityOk) || (observability.isError && analyticsOk),
    [analytics.isError, observability.isError, analyticsOk, observabilityOk]
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
  };

  return {
    analytics,
    observability,
    isLoading,
    isAnalyticsLoading,
    isObservabilityLoading,
    analyticsError,
    observabilityError,
    hasPartialFailure,
    hasMixedLoadedData,
    refetchAll,
  };
}
