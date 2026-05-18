/**
 * Unified analytics shell — positions metrics, run observability, and compare entry points.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Typography } from '@mui/material';
import { PageHeader } from '../../components/shell';
import { ErrorAlert } from '../../components/ui';
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import { defaultDateRange } from '../analytics/adapters/metricsFormatters';
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
import { useAnalyticsDashboardData } from './hooks/useAnalyticsDashboardData';
import {
  buildFilterParams,
  type AnalyticsDashboardFilters,
  type AnalyticsDashboardTab,
} from './types';

function initialFilters(): AnalyticsDashboardFilters {
  const range = defaultDateRange();
  return {
    dateFrom: range.from,
    dateTo: range.to,
    inventoryId: '',
    aisleId: '',
    clientId: '',
    clientSupplierId: '',
    providerName: '',
    modelName: '',
  };
}

export default function AnalyticsDashboardPage() {
  const { t } = useTranslation();
  const [draftFilters, setDraftFilters] = useState(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState(initialFilters);
  const [activeTab, setActiveTab] = useState<AnalyticsDashboardTab>('summary');

  const filterParams = useMemo(() => buildFilterParams(appliedFilters), [appliedFilters]);

  const { analytics, observability, isAnalyticsLoading, isObservabilityLoading, analyticsError, observabilityError, hasPartialData, refetchAll } =
    useAnalyticsDashboardData(filterParams);

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

  const observabilityDq = observability.data?.data_quality;

  return (
    <Box sx={{ pb: 4, width: '100%', minWidth: 0, maxWidth: '100%', overflowX: 'hidden', boxSizing: 'border-box' }}>
      <PageHeader a11yTitle={t('analyticsDashboard.page_a11y')} />

      <Typography variant="h5" component="h1" sx={{ mb: 0.5 }} data-testid="analytics-dashboard-title">
        {t('analyticsDashboard.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('analyticsDashboard.subtitle')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {t('analyticsDashboard.helper')}
      </Typography>

      <AnalyticsFilterBar
        filters={draftFilters}
        onChange={setDraftFilters}
        onApply={() => {
          setAppliedFilters(draftFilters);
          refetchAll();
        }}
        onReset={() => {
          const next = initialFilters();
          setDraftFilters(next);
          setAppliedFilters(next);
        }}
        inventories={inventories}
        aisles={aisles}
        inventoriesLoadFailed={inventoriesQuery.isError}
        isRefreshing={isAnalyticsLoading || isObservabilityLoading}
      />

      {analyticsError ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="analytics-partial-analytics-failed">
          {t('analyticsDashboard.partial.analyticsFailed')}
        </Alert>
      ) : null}
      {observabilityError ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="analytics-partial-observability-failed">
          {t('analyticsDashboard.partial.observabilityFailed')}
        </Alert>
      ) : null}
      {hasPartialData && !analyticsError && !observabilityError ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('analyticsDashboard.filters.partialScopeNote')}
        </Alert>
      ) : null}
      {observabilityDq && observabilityDq.jobs_without_audit_snapshot > 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('analyticsDashboard.partial.observabilityNoSnapshot')}
        </Alert>
      ) : null}

      {analyticsError && observabilityError ? (
        <ErrorAlert error={analyticsError} context="analytics" onRetry={() => refetchAll()} />
      ) : null}

      <AnalyticsTabs value={activeTab} onChange={setActiveTab} />

      {activeTab === 'summary' ? (
        <AnalyticsOverviewTab
          summary={analytics.summary}
          observability={observability.data}
          isAnalyticsLoading={isAnalyticsLoading}
          isObservabilityLoading={isObservabilityLoading}
        />
      ) : null}

      {activeTab === 'quality' ? <AnalyticsQualityTab analytics={analytics} isLoading={isAnalyticsLoading} /> : null}

      {activeTab === 'time' ? (
        <AnalyticsTimeTab analytics={analytics} observability={observability.data} isLoading={isAnalyticsLoading} />
      ) : null}

      {activeTab === 'providers' ? <AnalyticsProvidersTab observability={observability.data} /> : null}

      {activeTab === 'inventories' ? (
        <AnalyticsInventoriesTab
          analytics={analytics}
          isLoading={isAnalyticsLoading}
          inventoryProcessingModeById={inventoryProcessingModeById}
        />
      ) : null}

      {activeTab === 'aisles' ? (
        <AnalyticsAislesTab
          analytics={analytics}
          isLoading={isAnalyticsLoading}
          inventoryProcessingModeById={inventoryProcessingModeById}
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

      {activeTab === 'costs' ? <AnalyticsCostsTab onGoToCompare={() => setActiveTab('compare')} /> : null}
    </Box>
  );
}
