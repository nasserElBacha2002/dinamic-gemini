/**
 * Unified analytics shell — positions metrics, run observability, and compare entry points.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Alert, Box, Typography } from '@mui/material';
import { PageHeader } from '../../components/shell';
import { ErrorAlert } from '../../components/ui';
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import {
  ANALYTICS_TAB_QUERY_KEY,
  analyticsTabToUrl,
  parseAnalyticsTab,
} from '../../constants/analyticsTabs';
import {
  analyticsSearchParamsEqual,
  areAnalyticsFiltersEqual,
  clearAnalyticsFilterSearchParams,
  createDefaultAnalyticsFilters,
  parseAnalyticsFiltersFromSearchParams,
  writeAnalyticsFiltersToSearchParams,
} from '../../constants/analyticsFilters';
import { AnalyticsFilterBar } from './components/AnalyticsFilterBar';
import { AnalyticsTabs } from './components/AnalyticsTabs';
import { AnalyticsOverviewTab } from './components/AnalyticsOverviewTab';
import { AnalyticsQualityTab } from './components/AnalyticsQualityTab';
import { AnalyticsTimeTab } from './components/AnalyticsTimeTab';
import { AnalyticsProvidersTab } from './components/AnalyticsProvidersTab';
import { AnalyticsInventoriesTab } from './components/AnalyticsInventoriesTab';
import { AnalyticsAislesTab } from './components/AnalyticsAislesTab';
import { AnalyticsCompareTab } from './components/AnalyticsCompareTab';
import { AnalyticsCostsTab } from './components/AnalyticsCostsTab';
import { AnalyticsDataQualitySummary } from './components/AnalyticsDataQualitySummary';
import { useAnalyticsDashboardData } from './hooks/useAnalyticsDashboardData';
import { AnalyticsDrilldownDrawer } from './components/drilldown/AnalyticsDrilldownDrawer';
import {
  buildFilterParams,
  type AnalyticsDashboardFilters,
  type AnalyticsDashboardTab,
  type AnalyticsDrilldownHandlers,
  type AnalyticsDrilldownState,
} from './types';

export default function AnalyticsDashboardPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const defaultFilters = useMemo(() => createDefaultAnalyticsFilters(), []);

  const urlFilters = useMemo(
    () => parseAnalyticsFiltersFromSearchParams(searchParams, defaultFilters),
    [searchParams, defaultFilters]
  );

  const activeTab = useMemo(
    () => parseAnalyticsTab(searchParams.get(ANALYTICS_TAB_QUERY_KEY)),
    [searchParams]
  );

  const [draftFilters, setDraftFilters] = useState(urlFilters);
  const [appliedFilters, setAppliedFilters] = useState(urlFilters);
  const [drilldown, setDrilldown] = useState<AnalyticsDrilldownState>(null);

  useEffect(() => {
    setAppliedFilters((current) => (areAnalyticsFiltersEqual(current, urlFilters) ? current : urlFilters));
    setDraftFilters((current) => (areAnalyticsFiltersEqual(current, urlFilters) ? current : urlFilters));
  }, [urlFilters]);

  const writeFiltersToParams = useCallback(
    (base: URLSearchParams, filters: AnalyticsDashboardFilters, tab: AnalyticsDashboardTab): URLSearchParams => {
      const next = writeAnalyticsFiltersToSearchParams(base, filters, defaultFilters);
      next.set(ANALYTICS_TAB_QUERY_KEY, analyticsTabToUrl(tab));
      return next;
    },
    [defaultFilters]
  );

  useEffect(() => {
    const canonicalTab = analyticsTabToUrl(activeTab);
    const canonical = writeFiltersToParams(new URLSearchParams(searchParams), urlFilters, activeTab);
    const rawTab = searchParams.get(ANALYTICS_TAB_QUERY_KEY);
    const needsTabFix = rawTab !== canonicalTab;
    const needsFilterFix = !analyticsSearchParamsEqual(searchParams, canonical);
    if (!needsTabFix && !needsFilterFix) {
      return;
    }
    setSearchParams(canonical, { replace: true });
  }, [activeTab, searchParams, setSearchParams, urlFilters, writeFiltersToParams]);

  const pushFiltersToUrl = useCallback(
    (filters: AnalyticsDashboardFilters, tab: AnalyticsDashboardTab, replace: boolean) => {
      setSearchParams((prev) => writeFiltersToParams(new URLSearchParams(prev), filters, tab), { replace });
    },
    [setSearchParams, writeFiltersToParams]
  );

  const handleTabChange = useCallback(
    (tab: AnalyticsDashboardTab) => {
      setDrilldown(null);
      pushFiltersToUrl(appliedFilters, tab, false);
    },
    [appliedFilters, pushFiltersToUrl]
  );

  const filterParams = useMemo(() => buildFilterParams(appliedFilters), [appliedFilters]);

  const {
    analytics,
    observability,
    costSummary,
    isAnalyticsLoading,
    isObservabilityLoading,
    isCostSummaryLoading,
    analyticsError,
    observabilityError,
    costSummaryError,
    hasMixedLoadedData,
    hasPartialFailure,
    refetchAll,
  } = useAnalyticsDashboardData(filterParams);

  const inventoriesQuery = useInventoriesList({ page: 1, page_size: 200, sort_by: 'name', sort_dir: 'asc' });
  const inventories = useMemo(() => inventoriesQuery.data?.items ?? [], [inventoriesQuery.data?.items]);
  const aislesQuery = useAislesList(appliedFilters.inventoryId || undefined, {
    enabled: Boolean(appliedFilters.inventoryId),
  });
  const aisles = aislesQuery.data?.items ?? [];

  const inventoryProcessingModeById = useMemo(() => {
    const map = new Map<string, string | undefined>();
    for (const inv of inventories) {
      map.set(inv.id, inv.processing_mode);
    }
    return map;
  }, [inventories]);

  const selectedInventory = inventories.find((inv) => inv.id === appliedFilters.inventoryId) ?? null;

  const inventoriesById = useMemo(() => {
    const map = new Map<string, (typeof inventories)[number]>();
    for (const inv of inventories) {
      map.set(inv.id, inv);
    }
    return map;
  }, [inventories]);

  const drilldownHandlers: AnalyticsDrilldownHandlers = useMemo(
    () => ({
      onOpenInventoryDrilldown: (inventoryId) => setDrilldown({ type: 'inventory', inventoryId }),
      onOpenAisleDrilldown: (inventoryId, aisleId) => setDrilldown({ type: 'aisle', inventoryId, aisleId }),
    }),
    []
  );

  return (
    <Box sx={{ pb: 4, width: '100%', minWidth: 0, maxWidth: '100%', overflowX: 'hidden', boxSizing: 'border-box' }}>
      <PageHeader a11yTitle={t('analyticsDashboard.page_a11y')} />

      <Typography variant="h5" component="h1" sx={{ mb: 0.5 }} data-testid="analytics-dashboard-title">
        {t('analyticsDashboard.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('analyticsDashboard.subtitle')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {t('analyticsDashboard.helper')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {t('analyticsDashboard.visual.scopeNote')}
      </Typography>

      <AnalyticsDataQualitySummary
        costSummary={costSummary.data}
        observability={observability.data}
        analyticsError={Boolean(analyticsError)}
        observabilityError={Boolean(observabilityError)}
        costSummaryError={Boolean(costSummaryError)}
      />

      <AnalyticsFilterBar
        filters={draftFilters}
        onChange={setDraftFilters}
        onApply={() => {
          setAppliedFilters(draftFilters);
          pushFiltersToUrl(draftFilters, activeTab, false);
        }}
        onReset={() => {
          const next = createDefaultAnalyticsFilters();
          setDraftFilters(next);
          setAppliedFilters(next);
          setSearchParams(
            (prev) => {
              const cleared = clearAnalyticsFilterSearchParams(prev);
              cleared.set(ANALYTICS_TAB_QUERY_KEY, analyticsTabToUrl(activeTab));
              return cleared;
            },
            { replace: false }
          );
        }}
        inventories={inventories}
        aisles={aisles}
        inventoriesLoadFailed={inventoriesQuery.isError}
        isRefreshing={isAnalyticsLoading || isObservabilityLoading || isCostSummaryLoading}
      />

      {hasMixedLoadedData ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="analytics-mixed-loaded-data">
          {t('analyticsDashboard.filters.partialScopeNote')}
        </Alert>
      ) : null}
      {hasPartialFailure && costSummaryError && !analyticsError && !observabilityError ? (
        <Alert severity="info" variant="outlined" sx={{ mb: 2 }} data-testid="analytics-partial-cost-failed">
          {t('analyticsDashboard.partial.costFailed')}
        </Alert>
      ) : null}
      {analyticsError && observabilityError ? (
        <ErrorAlert error={analyticsError} context="analytics" onRetry={() => refetchAll()} />
      ) : null}

      <AnalyticsTabs value={activeTab} onChange={handleTabChange} />

      {activeTab === 'summary' ? (
        <AnalyticsOverviewTab
          analytics={analytics}
          summary={analytics.summary}
          observability={observability.data}
          costSummary={costSummary.data}
          isAnalyticsLoading={isAnalyticsLoading}
          isObservabilityLoading={isObservabilityLoading}
          isCostSummaryLoading={isCostSummaryLoading}
          isCostSummaryError={Boolean(costSummaryError)}
          inventoryProcessingModeById={inventoryProcessingModeById}
          drilldown={drilldownHandlers}
        />
      ) : null}

      {activeTab === 'quality' ? <AnalyticsQualityTab analytics={analytics} isLoading={isAnalyticsLoading} /> : null}

      {activeTab === 'time' ? (
        <AnalyticsTimeTab analytics={analytics} observability={observability.data} isLoading={isAnalyticsLoading} />
      ) : null}

      {activeTab === 'providers' ? (
        <AnalyticsProvidersTab observability={observability.data} costSummary={costSummary.data} />
      ) : null}

      {activeTab === 'inventories' ? (
        <AnalyticsInventoriesTab
          analytics={analytics}
          costSummary={costSummary.data}
          isLoading={isAnalyticsLoading}
          isCostLoading={isCostSummaryLoading}
          inventoryProcessingModeById={inventoryProcessingModeById}
          drilldown={drilldownHandlers}
        />
      ) : null}

      {activeTab === 'aisles' ? (
        <AnalyticsAislesTab
          analytics={analytics}
          costSummary={costSummary.data}
          isLoading={isAnalyticsLoading}
          isCostLoading={isCostSummaryLoading}
          inventoryProcessingModeById={inventoryProcessingModeById}
          drilldown={drilldownHandlers}
        />
      ) : null}

      {activeTab === 'compare' ? (
        <AnalyticsCompareTab
          inventoryId={appliedFilters.inventoryId}
          aisleId={appliedFilters.aisleId}
          inventoryName={selectedInventory?.name ?? null}
          processingMode={selectedInventory?.processing_mode}
        />
      ) : null}

      {activeTab === 'costs' ? (
        <AnalyticsCostsTab
          costSummary={costSummary.data}
          isLoading={isCostSummaryLoading}
          isError={Boolean(costSummaryError)}
          onGoToCompare={() => handleTabChange('compare')}
          drilldown={drilldownHandlers}
        />
      ) : null}

      <AnalyticsDrilldownDrawer
        state={drilldown}
        onClose={() => setDrilldown(null)}
        analytics={analytics}
        costSummary={costSummary.data}
        isCostLoading={isCostSummaryLoading}
        inventoryProcessingModeById={inventoryProcessingModeById}
        inventoriesById={inventoriesById}
        onOpenAisleDrilldown={drilldownHandlers.onOpenAisleDrilldown}
      />
    </Box>
  );
}
