import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid, Typography } from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { orderQualityRows } from '../../analytics/adapters/metricsViewModel';
import {
  buildExecutivePositionKpis,
  buildExecutiveRunKpis,
  buildUnavailableGlobalCostKpis,
  hasUnidentifiedProductRate,
} from '../adapters/analyticsDashboardViewModel';
import {
  buildAutoVsManualSegments,
  buildProcessingTimeByInventoryData,
  buildProviderRunVolumeChartData,
  buildQualityIssueChartData,
  buildTopAislesAttention,
  SUMMARY_ATTENTION_TOP_N,
} from '../adapters/analyticsChartDatasets';
import { buildCostWarnings, buildOverviewCostKpis, hasCostData } from '../adapters/analyticsCostViewModel';
import type { AnalyticsDrilldownHandlers } from '../types';
import { AnalyticsCostVisualSection } from './AnalyticsCostVisualSection';
import { AnalyticsChartCard } from './AnalyticsChartCard';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { AnalyticsSummaryAttentionList } from './AnalyticsSummaryAttentionList';
import { ExecutiveKpiStrip } from './ExecutiveKpiStrip';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import { SegmentBarChart } from './charts/SegmentBarChart';
import TrendBars from '../../analytics/components/TrendBars';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsOverviewTabProps {
  analytics: AnalyticsBundle;
  summary: AnalyticsBundle['summary'];
  observability: ObservabilityMetricsResponse | null | undefined;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isAnalyticsLoading: boolean;
  isObservabilityLoading: boolean;
  isCostSummaryLoading: boolean;
  isCostSummaryError: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  drilldown: AnalyticsDrilldownHandlers;
}

export function AnalyticsOverviewTab({
  analytics,
  summary,
  observability,
  costSummary,
  isAnalyticsLoading,
  isObservabilityLoading,
  isCostSummaryLoading,
  isCostSummaryError,
  inventoryProcessingModeById,
  drilldown,
}: AnalyticsOverviewTabProps) {
  const { t } = useTranslation();
  const unidentified = hasUnidentifiedProductRate(summary);
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const loadingText = t('analyticsDashboard.visual.loadingChart');

  const positionKpis = useMemo(
    () => buildExecutivePositionKpis(summary, unidentified, t),
    [summary, unidentified, t]
  );
  const runKpis = useMemo(() => buildExecutiveRunKpis(observability, t), [observability, t]);

  const costHasData = hasCostData(costSummary) && !isCostSummaryError;

  const costKpis = useMemo(() => {
    if (isCostSummaryLoading) {
      return [];
    }
    if (isCostSummaryError || !hasCostData(costSummary)) {
      return buildUnavailableGlobalCostKpis(t).slice(0, 4).map((c) => ({
        ...c,
        grainLabel: t('analyticsDashboard.costs.sectionTitle'),
      }));
    }
    return buildOverviewCostKpis(costSummary, t).map((c) => ({
      ...c,
      grainLabel: t('analyticsDashboard.costs.sectionTitle'),
    }));
  }, [costSummary, isCostSummaryError, isCostSummaryLoading, t]);

  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);

  const qualityChart = useMemo(
    () => buildQualityIssueChartData(orderQualityRows(analytics.quality?.items ?? [])),
    [analytics.quality?.items]
  );
  const autoManual = useMemo(() => buildAutoVsManualSegments(summary, t), [summary, t]);
  const processingByInv = useMemo(
    () => buildProcessingTimeByInventoryData(analytics.inventoryPerformance?.items ?? []),
    [analytics.inventoryPerformance?.items]
  );
  const providerRunVolume = useMemo(() => buildProviderRunVolumeChartData(observability), [observability]);
  const topAisles = useMemo(
    () => buildTopAislesAttention(analytics.aisleIssues?.items ?? [], SUMMARY_ATTENTION_TOP_N),
    [analytics.aisleIssues?.items]
  );

  const showCostSection = (costHasData || isCostSummaryLoading) && !isCostSummaryError;

  return (
    <Box data-testid="analytics-overview-tab">
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }} data-testid="analytics-summary-hero-title">
        {t('analyticsDashboard.visual.executiveOverview')}
      </Typography>

      <ExecutiveKpiStrip
        positionTitle={t('analyticsDashboard.grain_positions')}
        runTitle={t('analyticsDashboard.grain_runs')}
        costTitle={t('analyticsDashboard.costs.sectionTitle')}
        positionKpis={positionKpis}
        runKpis={runKpis}
        costKpis={costKpis}
        isPositionLoading={isAnalyticsLoading}
        isRunLoading={isObservabilityLoading}
        isCostLoading={isCostSummaryLoading}
        hasPositionData={Boolean(summary)}
        hasRunData={Boolean(observability?.totals)}
        hasCostData={costHasData}
      />

      {showCostSection ? (
        <AnalyticsSectionCard
          title={t('analyticsDashboard.visual.costSnapshot')}
          subtitle={t('analyticsDashboard.costs.llmCostHint')}
        >
          {costWarnings.length > 0 ? (
            <Typography variant="caption" color="warning.main" display="block" sx={{ mb: 1.5 }}>
              {costWarnings[0]?.label}
              {costWarnings.length > 1 ? ` (+${costWarnings.length - 1})` : ''}
            </Typography>
          ) : null}
          <AnalyticsCostVisualSection costSummary={costSummary} isLoading={isCostSummaryLoading} compact />
        </AnalyticsSectionCard>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} lg={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.qualitySnapshot')}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <AnalyticsChartCard
                  title={t('analyticsDashboard.visual.autoVsManual')}
                  loading={isAnalyticsLoading}
                  loadingText={loadingText}
                  data-testid="analytics-chart-auto-manual"
                >
                  <SegmentBarChart
                    segments={autoManual}
                    emptyText={emptyText}
                    data-testid="analytics-chart-auto-manual-bars"
                  />
                </AnalyticsChartCard>
              </Grid>
              <Grid item xs={12}>
                <AnalyticsChartCard
                  title={t('analyticsDashboard.visual.qualityIssues')}
                  loading={isAnalyticsLoading}
                  loadingText={loadingText}
                  empty={!isAnalyticsLoading && !qualityChart.length}
                  emptyText={emptyText}
                  data-testid="analytics-chart-quality-issues"
                >
                  <HorizontalBarChart
                    data={qualityChart}
                    emptyText={emptyText}
                    ariaLabel={t('analyticsDashboard.visual.qualityIssues')}
                    data-testid="analytics-chart-quality-issues-bars"
                  />
                </AnalyticsChartCard>
              </Grid>
            </Grid>
          </AnalyticsSectionCard>
        </Grid>

        <Grid item xs={12} lg={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.timeSnapshot')}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <AnalyticsChartCard
                  title={t('analyticsDashboard.visual.processingTimeByInventory')}
                  loading={isAnalyticsLoading}
                  loadingText={loadingText}
                  empty={!isAnalyticsLoading && !processingByInv.length}
                  emptyText={emptyText}
                  data-testid="analytics-chart-processing-inventory"
                >
                  <HorizontalBarChart
                    data={processingByInv}
                    emptyText={emptyText}
                    barColor="secondary.main"
                    ariaLabel={t('analyticsDashboard.visual.processingTimeByInventory')}
                    data-testid="analytics-chart-processing-inventory-bars"
                    onBarClick={(item) => drilldown.onOpenInventoryDrilldown(item.id)}
                  />
                </AnalyticsChartCard>
              </Grid>
              <Grid item xs={12}>
                <AnalyticsChartCard
                  title={t('analyticsDashboard.time.trendTitle')}
                  loading={isAnalyticsLoading}
                  loadingText={loadingText}
                  empty={!isAnalyticsLoading && !(analytics.trends?.reviewed_results_over_time?.length ?? 0)}
                  emptyText={emptyText}
                  data-testid="analytics-chart-processing-trend"
                >
                  <TrendBars
                    title={t('analyticsDashboard.time.trendTitle')}
                    points={analytics.trends?.reviewed_results_over_time ?? []}
                    emptyMessage={emptyText}
                    hideTitle
                  />
                </AnalyticsChartCard>
              </Grid>
            </Grid>
          </AnalyticsSectionCard>
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} lg={6}>
          <AnalyticsSectionCard
            title={t('analyticsDashboard.visual.providerSnapshot')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
          >
            <AnalyticsChartCard
              title={t('analyticsDashboard.visual.providerRunVolume')}
              loading={isObservabilityLoading}
              loadingText={loadingText}
              empty={!isObservabilityLoading && !providerRunVolume.length}
              emptyText={emptyText}
              data-testid="analytics-chart-provider-run-volume"
            >
              <HorizontalBarChart
                data={providerRunVolume}
                emptyText={emptyText}
                ariaLabel={t('analyticsDashboard.visual.providerRunVolume')}
                data-testid="analytics-chart-provider-run-volume-bars"
              />
            </AnalyticsChartCard>
          </AnalyticsSectionCard>
        </Grid>

        <Grid item xs={12} lg={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.aislesAttention')}>
            <AnalyticsSummaryAttentionList
              rows={topAisles}
              inventoryProcessingModeById={inventoryProcessingModeById}
              onOpenAisleDrilldown={drilldown.onOpenAisleDrilldown}
              emptyText={emptyText}
            />
          </AnalyticsSectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}
