import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ROUTE_ANALITICA } from '../../../constants/appRoutes';
import { ANALYTICS_TAB_QUERY_KEY, analyticsTabToUrl } from '../../../constants/analyticsTabs';
import type { AnalyticsDashboardTab } from '../types';

export function useAnalyticsTabHref() {
  const [searchParams] = useSearchParams();

  return useCallback(
    (tab: AnalyticsDashboardTab) => {
      const next = new URLSearchParams(searchParams);
      next.set(ANALYTICS_TAB_QUERY_KEY, analyticsTabToUrl(tab));
      return `${ROUTE_ANALITICA}?${next.toString()}`;
    },
    [searchParams]
  );
}
