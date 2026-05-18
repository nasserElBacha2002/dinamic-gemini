import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsSummaryResponse } from '../../analytics/types';
import { AnalyticsKpiGrid } from './AnalyticsKpiGrid';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { MetricUnavailableCards } from './MetricUnavailableState';
import {
  buildPositionSummaryKpis,
  buildRunSummaryKpis,
  buildUnavailableGlobalCostKpis,
  hasUnidentifiedProductRate,
} from '../adapters/analyticsDashboardViewModel';

export interface AnalyticsOverviewTabProps {
  summary: AnalyticsSummaryResponse | null | undefined;
  observability: ObservabilityMetricsResponse | null | undefined;
  isAnalyticsLoading: boolean;
  isObservabilityLoading: boolean;
}

export function AnalyticsOverviewTab({
  summary,
  observability,
  isAnalyticsLoading,
  isObservabilityLoading,
}: AnalyticsOverviewTabProps) {
  const { t } = useTranslation();
  const unidentified = hasUnidentifiedProductRate(summary);

  const positionKpis = useMemo(
    () => buildPositionSummaryKpis(summary, unidentified, t),
    [summary, unidentified, t]
  );
  const runKpis = useMemo(() => buildRunSummaryKpis(observability, t), [observability, t]);
  const unavailableCosts = useMemo(() => buildUnavailableGlobalCostKpis(t), [t]);

  return (
    <Box>
      <AnalyticsSectionCard
        title={t('analyticsDashboard.grain_positions')}
        grainLabel={t('analyticsDashboard.grain_positions')}
      >
        <AnalyticsKpiGrid
          cards={positionKpis}
          isLoading={isAnalyticsLoading}
          hasData={Boolean(summary)}
          skeletonCount={unidentified ? 7 : 6}
        />
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.grain_runs')} grainLabel={t('analyticsDashboard.grain_runs')}>
        <AnalyticsKpiGrid
          cards={runKpis}
          isLoading={isObservabilityLoading}
          hasData={Boolean(observability?.totals)}
          skeletonCount={8}
        />
      </AnalyticsSectionCard>

      <AnalyticsSectionCard
        title={t('analyticsDashboard.costs.globalUnavailableTitle')}
        subtitle={t('analyticsDashboard.costs.unavailableExplain')}
      >
        <MetricUnavailableCards
          cards={unavailableCosts.map((c) => ({
            label: c.label,
            value: String(c.value),
            description: c.description,
          }))}
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }} data-testid="global-cost-unavailable-note">
          {t('analyticsDashboard.costs.globalUnavailableDescription')}
        </Typography>
      </AnalyticsSectionCard>
    </Box>
  );
}
