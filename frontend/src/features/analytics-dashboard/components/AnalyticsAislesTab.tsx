import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import {
  buildAislePendingReviewChartData,
  buildCostByAisleChartData,
  buildTopAislesAttention,
  CHART_TOP_N,
} from '../adapters/analyticsChartDatasets';
import { buildCostByAisleLookup, buildCostWarnings } from '../adapters/analyticsCostViewModel';
import { buildAisleEntityKey } from '../adapters/aisleEntityKeys';
import { buildAisleRankingCardItems } from '../adapters/entityRankingViewModels';
import { AnalyticsEntityRankingCards } from './rankings/AnalyticsEntityRankingCards';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import type { AnalyticsDrilldownHandlers } from '../types';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsAislesTabProps {
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  drilldown: AnalyticsDrilldownHandlers;
}

export function AnalyticsAislesTab({
  analytics,
  costSummary,
  isLoading,
  isCostLoading,
  inventoryProcessingModeById,
  drilldown,
}: AnalyticsAislesTabProps) {
  const { t } = useTranslation();
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const loadingText = t('analyticsDashboard.visual.loadingChart');
  const aisleRows = analytics.aisleIssues?.items ?? [];

  const costByAisle = useMemo(() => buildCostByAisleLookup(costSummary), [costSummary]);
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const costChart = useMemo(() => buildCostByAisleChartData(costSummary), [costSummary]);
  const pendingChart = useMemo(
    () => buildAislePendingReviewChartData(aisleRows, t, CHART_TOP_N),
    [aisleRows, t]
  );
  const topAisles = useMemo(() => buildTopAislesAttention(aisleRows, CHART_TOP_N), [aisleRows]);
  const rankingItems = useMemo(
    () =>
      buildAisleRankingCardItems({
        rows: topAisles,
        costByAisle,
        isCostLoading,
        inventoryProcessingModeById,
        onOpenAisleDrilldown: drilldown.onOpenAisleDrilldown,
        t,
      }),
    [topAisles, costByAisle, isCostLoading, inventoryProcessingModeById, drilldown.onOpenAisleDrilldown, t]
  );

  return (
    <Box data-testid="analytics-aisles-tab">
      {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.topAislesByCost')}
            data-testid="analytics-aisles-panel-cost"
          >
            {isCostLoading ? (
              <Box data-testid="analytics-aisles-cost-summary-loading">{loadingText}</Box>
            ) : (
              <HorizontalBarChart
                data={costChart}
                emptyText={emptyText}
                ariaLabel={t('analyticsDashboard.visual.topAislesByCost')}
                data-testid="analytics-aisles-cost-summary-bars"
                onBarClick={(item) => {
                  const row = aisleRows.find(
                    (a) => buildAisleEntityKey(a.inventory_id, a.aisle_id) === item.id
                  );
                  if (row) drilldown.onOpenAisleDrilldown(row.inventory_id, row.aisle_id);
                }}
              />
            )}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.aisles.pendingChart')}
            isLoading={isLoading}
            data-testid="analytics-aisles-panel-pending"
          >
            <HorizontalBarChart
              data={pendingChart}
              emptyText={emptyText}
              barColor="warning.main"
              data-testid="analytics-aisles-chart-pending"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.aisles.attentionTitle')}
            isLoading={isLoading}
            data-testid="analytics-aisles-panel-attention"
          >
            <AnalyticsEntityRankingCards
              items={rankingItems}
              emptyText={emptyText}
              testId="analytics-aisles-ranking"
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
