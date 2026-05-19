import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { AnalyticsInventoryRankingCards } from './AnalyticsInventoryRankingCards';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import {
  buildCostByInventoryChartData,
  buildInventoryAutoAcceptChartData,
  buildInventoryCostPerUnitChartData,
  buildProcessingTimeByInventoryData,
  buildTopInventoryPerformanceRows,
} from '../adapters/analyticsChartDatasets';
import { buildCostByInventoryLookup, buildCostWarnings } from '../adapters/analyticsCostViewModel';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import type { AnalyticsDrilldownHandlers } from '../types';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsInventoriesTabProps {
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  drilldown: AnalyticsDrilldownHandlers;
}

export function AnalyticsInventoriesTab({
  analytics,
  costSummary,
  isLoading,
  isCostLoading,
  inventoryProcessingModeById,
  drilldown,
}: AnalyticsInventoriesTabProps) {
  const { t } = useTranslation();
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const loadingText = t('analyticsDashboard.visual.loadingChart');

  const costByInventory = useMemo(() => buildCostByInventoryLookup(costSummary), [costSummary]);
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const costChart = useMemo(() => buildCostByInventoryChartData(costSummary), [costSummary]);
  const autoAcceptChart = useMemo(
    () => buildInventoryAutoAcceptChartData(analytics.inventoryPerformance?.items ?? []),
    [analytics.inventoryPerformance?.items]
  );
  const costPerUnitChart = useMemo(() => buildInventoryCostPerUnitChartData(costSummary), [costSummary]);
  const timeChart = useMemo(
    () => buildProcessingTimeByInventoryData(analytics.inventoryPerformance?.items ?? []),
    [analytics.inventoryPerformance?.items]
  );
  const topInventories = useMemo(
    () => buildTopInventoryPerformanceRows(analytics.inventoryPerformance?.items ?? []),
    [analytics.inventoryPerformance?.items]
  );

  return (
    <Box data-testid="analytics-inventories-tab">
      {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.topInventoriesByCost')}
            data-testid="analytics-inventories-panel-cost"
          >
            {isCostLoading ? (
              <Box data-testid="analytics-inventories-cost-summary-loading">{loadingText}</Box>
            ) : (
              <HorizontalBarChart
                data={costChart}
                emptyText={emptyText}
                ariaLabel={t('analyticsDashboard.visual.topInventoriesByCost')}
                data-testid="analytics-inventories-cost-summary-bars"
                onBarClick={(item) => drilldown.onOpenInventoryDrilldown(item.id)}
              />
            )}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.inventories.rankingTitle')}
            isLoading={isLoading}
            data-testid="analytics-inventories-panel-ranking"
          >
            <AnalyticsInventoryRankingCards
              rows={topInventories}
              costSummary={costSummary}
              costByInventory={costByInventory}
              isCostLoading={isCostLoading}
              inventoryProcessingModeById={inventoryProcessingModeById}
              onOpenInventoryDrilldown={drilldown.onOpenInventoryDrilldown}
              emptyText={emptyText}
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.inventories.autoAcceptChart')}
            isLoading={isLoading}
            data-testid="analytics-inventories-panel-auto-accept"
          >
            <HorizontalBarChart
              data={autoAcceptChart}
              emptyText={emptyText}
              data-testid="analytics-inventories-chart-auto-accept"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.inventories.costPerUnitChart')}
            isLoading={isCostLoading}
            data-testid="analytics-inventories-panel-cost-per-unit"
          >
            <HorizontalBarChart
              data={costPerUnitChart}
              emptyText={emptyText}
              data-testid="analytics-inventories-chart-cost-per-unit"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.processingTimeByInventory')}
            isLoading={isLoading}
            data-testid="analytics-inventories-panel-time"
          >
            <HorizontalBarChart
              data={timeChart}
              emptyText={emptyText}
              barColor="secondary.main"
              data-testid="analytics-inventories-chart-time"
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
