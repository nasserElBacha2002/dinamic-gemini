import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid, Typography } from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { orderQualityRows } from '../../analytics/adapters/metricsViewModel';
import { buildHeroExecutiveKpis } from '../adapters/analyticsDashboardViewModel';
import {
  buildAutoVsManualDonutSegments,
  buildPrimaryQualityIssue,
  buildProviderRunVolumeChartData,
  buildSlowestInventoryInsight,
  buildTopAislesAttention,
  buildTopProviderInsight,
  SUMMARY_ATTENTION_TOP_N,
} from '../adapters/analyticsChartDatasets';
import { buildCostWarnings, hasCostData } from '../adapters/analyticsCostViewModel';
import type { AnalyticsDrilldownHandlers } from '../types';
import { useAnalyticsTabHref } from '../hooks/useAnalyticsTabHref';
import { AnalyticsExecutiveHero } from './AnalyticsExecutiveHero';
import { AnalyticsSummaryAttentionList } from './AnalyticsSummaryAttentionList';
import { AnalyticsSummaryCostInsight } from './AnalyticsSummaryCostInsight';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { DonutChart } from './charts/DonutChart';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
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
  const tabHref = useAnalyticsTabHref();
  const emptyText = t('analyticsDashboard.visual.emptyChart');

  const costHasData = hasCostData(costSummary) && !isCostSummaryError;
  const heroLoading = isAnalyticsLoading || isObservabilityLoading || isCostSummaryLoading;
  const heroHasData = Boolean(summary) || Boolean(observability?.totals) || costHasData;

  const heroKpis = useMemo(
    () =>
      buildHeroExecutiveKpis(summary, observability, costSummary, t, {
        costAvailable: costHasData,
      }),
    [summary, observability, costSummary, t, costHasData]
  );

  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const costWarningLine =
    costWarnings.length > 0
      ? `${costWarnings[0]?.label}${costWarnings.length > 1 ? ` (+${costWarnings.length - 1})` : ''}`
      : null;

  const qualityDonut = useMemo(() => buildAutoVsManualDonutSegments(summary, t), [summary, t]);
  const primaryIssue = useMemo(
    () => buildPrimaryQualityIssue(orderQualityRows(analytics.quality?.items ?? [])),
    [analytics.quality?.items]
  );

  const trendPoints = analytics.trends?.reviewed_results_over_time ?? [];
  const slowestInventory = useMemo(
    () => buildSlowestInventoryInsight(analytics.inventoryPerformance?.items ?? []),
    [analytics.inventoryPerformance?.items]
  );

  const topProvider = useMemo(() => buildTopProviderInsight(observability), [observability]);
  const providerMiniBars = useMemo(() => buildProviderRunVolumeChartData(observability), [observability]);

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

      <AnalyticsExecutiveHero kpis={heroKpis} isLoading={heroLoading} hasData={heroHasData} />

      <Grid container spacing={2}>
        {showCostSection ? (
          <Grid item xs={12} md={6}>
            <AnalyticsSummaryPanel
              title={t('analyticsDashboard.visual.costSnapshot')}
              subtitle={t('analyticsDashboard.costs.llmCostHint')}
              ctaLabel={t('analyticsDashboard.summary.viewCosts')}
              ctaHref={tabHref('costs')}
              isLoading={isCostSummaryLoading}
              data-testid="analytics-summary-panel-cost"
            >
              <AnalyticsSummaryCostInsight costSummary={costSummary} warningLine={costWarningLine} />
            </AnalyticsSummaryPanel>
          </Grid>
        ) : null}

        <Grid item xs={12} md={showCostSection ? 6 : 12} lg={showCostSection ? 6 : 4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.qualitySnapshot')}
            ctaLabel={t('analyticsDashboard.summary.viewQuality')}
            ctaHref={tabHref('quality')}
            isLoading={isAnalyticsLoading}
            data-testid="analytics-summary-panel-quality"
          >
            <DonutChart
              segments={qualityDonut}
              emptyText={emptyText}
              data-testid="analytics-summary-quality-donut"
            />
            {primaryIssue ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1.5 }}>
                {t('analyticsDashboard.summary.primaryIssue', { issue: primaryIssue })}
              </Typography>
            ) : null}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6} lg={showCostSection ? 6 : 4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.timeSnapshot')}
            ctaLabel={t('analyticsDashboard.summary.viewTime')}
            ctaHref={tabHref('time')}
            isLoading={isAnalyticsLoading}
            loadingSkeletonHeight={160}
            data-testid="analytics-summary-panel-time"
          >
            <Box data-testid="analytics-chart-processing-trend" sx={{ minHeight: 160 }}>
              <TrendBars
                title={t('analyticsDashboard.time.trendTitle')}
                points={trendPoints}
                emptyMessage={emptyText}
                hideTitle
              />
            </Box>
            {slowestInventory ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1.5 }}>
                {t('analyticsDashboard.summary.slowestInventory', {
                  name: slowestInventory.name,
                  minutes: slowestInventory.minutes.toFixed(1),
                })}
              </Typography>
            ) : null}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6} lg={showCostSection ? 6 : 4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.providerSnapshot')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
            ctaLabel={t('analyticsDashboard.summary.viewProviders')}
            ctaHref={tabHref('providers')}
            isLoading={isObservabilityLoading}
            data-testid="analytics-summary-panel-provider"
          >
            {topProvider ? (
              <Typography variant="body2" sx={{ mb: 1 }}>
                {t('analyticsDashboard.summary.topProvider', {
                  provider: topProvider.label,
                  runs: topProvider.runs,
                })}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {emptyText}
              </Typography>
            )}
            {providerMiniBars.length > 0 ? (
              <HorizontalBarChart
                data={providerMiniBars}
                emptyText={emptyText}
                ariaLabel={t('analyticsDashboard.visual.providerRunVolume')}
                data-testid="analytics-summary-provider-mini-bars"
              />
            ) : null}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6} lg={showCostSection ? 12 : 4}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.aislesAttention')}
            ctaLabel={t('analyticsDashboard.summary.viewAisles')}
            ctaHref={tabHref('aisles')}
            data-testid="analytics-summary-panel-attention"
          >
            <AnalyticsSummaryAttentionList
              rows={topAisles}
              inventoryProcessingModeById={inventoryProcessingModeById}
              onOpenAisleDrilldown={drilldown.onOpenAisleDrilldown}
              emptyText={emptyText}
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
