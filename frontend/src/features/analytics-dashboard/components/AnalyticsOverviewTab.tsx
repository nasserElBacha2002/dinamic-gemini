import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box } from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { AnalyticsSummaryResponse } from '../../analytics/types';
import { AnalyticsKpiGrid } from './AnalyticsKpiGrid';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import {
  buildPositionSummaryKpis,
  buildRunSummaryKpis,
  buildUnavailableGlobalCostKpis,
  hasUnidentifiedProductRate,
} from '../adapters/analyticsDashboardViewModel';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import { buildCostWarnings, buildOverviewCostKpis, hasCostData } from '../adapters/analyticsCostViewModel';

export interface AnalyticsOverviewTabProps {
  summary: AnalyticsSummaryResponse | null | undefined;
  observability: ObservabilityMetricsResponse | null | undefined;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isAnalyticsLoading: boolean;
  isObservabilityLoading: boolean;
  isCostSummaryLoading: boolean;
  isCostSummaryError: boolean;
}

export function AnalyticsOverviewTab({
  summary,
  observability,
  costSummary,
  isAnalyticsLoading,
  isObservabilityLoading,
  isCostSummaryLoading,
  isCostSummaryError,
}: AnalyticsOverviewTabProps) {
  const { t } = useTranslation();
  const unidentified = hasUnidentifiedProductRate(summary);

  const positionKpis = useMemo(
    () => buildPositionSummaryKpis(summary, unidentified, t),
    [summary, unidentified, t]
  );
  const runKpis = useMemo(() => buildRunSummaryKpis(observability, t), [observability, t]);
  const costKpis = useMemo(() => {
    if (isCostSummaryError || (!isCostSummaryLoading && !hasCostData(costSummary))) {
      return buildUnavailableGlobalCostKpis(t).slice(0, 5);
    }
    return buildOverviewCostKpis(costSummary, t);
  }, [costSummary, isCostSummaryError, isCostSummaryLoading, t]);

  const costHasData = hasCostData(costSummary) && !isCostSummaryError;
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);

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
        title={t('analyticsDashboard.costs.sectionTitle')}
        subtitle={
          costHasData
            ? t('analyticsDashboard.costs.llmCostHint')
            : t('analyticsDashboard.costs.unavailableExplain')
        }
      >
        {costHasData && costWarnings.length > 0 ? (
          <AnalyticsCostWarningsBlock warnings={costWarnings} compact />
        ) : null}
        <AnalyticsKpiGrid
          cards={costKpis}
          isLoading={isCostSummaryLoading}
          hasData={costHasData || isCostSummaryLoading}
          skeletonCount={5}
        />
      </AnalyticsSectionCard>
    </Box>
  );
}
