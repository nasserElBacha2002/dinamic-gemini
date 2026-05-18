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

  const hasPartialData = useMemo(() => {
    const analyticsOk = !analytics.isError && Boolean(analytics.summary);
    const observabilityOk = !observability.isError && Boolean(observability.data?.totals);
    return (analyticsOk && !observabilityOk) || (!analyticsOk && observabilityOk);
  }, [analytics.isError, analytics.summary, observability.isError, observability.data?.totals]);

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
    hasPartialData,
    refetchAll,
  };
}
