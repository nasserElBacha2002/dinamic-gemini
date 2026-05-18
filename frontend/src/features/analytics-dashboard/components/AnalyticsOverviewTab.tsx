import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid, Link as MuiLink, Paper, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { orderQualityRows } from '../../analytics/adapters/metricsViewModel';
import { pathToAislePositions } from '../../../constants/appRoutes';
import {
  buildPositionSummaryKpis,
  buildRunSummaryKpis,
  buildUnavailableGlobalCostKpis,
  hasUnidentifiedProductRate,
} from '../adapters/analyticsDashboardViewModel';
import {
  buildAutoVsManualSegments,
  buildProcessingTimeByInventoryData,
  buildProviderReliabilityChartData,
  buildQualityIssueChartData,
  buildTopAislesAttention,
} from '../adapters/analyticsChartDatasets';
import { buildCostWarnings, buildOverviewCostKpis, hasCostData } from '../adapters/analyticsCostViewModel';
import { AnalyticsCostVisualSection } from './AnalyticsCostVisualSection';
import { AnalyticsChartCard } from './AnalyticsChartCard';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
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
}: AnalyticsOverviewTabProps) {
  const { t } = useTranslation();
  const unidentified = hasUnidentifiedProductRate(summary);
  const emptyText = t('analyticsDashboard.visual.emptyChart');

  const positionKpis = useMemo(
    () => buildPositionSummaryKpis(summary, unidentified, t),
    [summary, unidentified, t]
  );
  const runKpis = useMemo(() => buildRunSummaryKpis(observability, t), [observability, t]);
  const costKpis = useMemo(() => {
    if (isCostSummaryError || (!isCostSummaryLoading && !hasCostData(costSummary))) {
      return buildUnavailableGlobalCostKpis(t).slice(0, 5).map((c) => ({
        ...c,
        grainLabel: t('analyticsDashboard.costs.sectionTitle'),
      }));
    }
    return buildOverviewCostKpis(costSummary, t).map((c) => ({
      ...c,
      grainLabel: t('analyticsDashboard.costs.sectionTitle'),
    }));
  }, [costSummary, isCostSummaryError, isCostSummaryLoading, t]);

  const costHasData = hasCostData(costSummary) && !isCostSummaryError;
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
  const providerReliability = useMemo(
    () => buildProviderReliabilityChartData(observability),
    [observability]
  );
  const topAisles = useMemo(
    () => buildTopAislesAttention(analytics.aisleIssues?.items ?? []),
    [analytics.aisleIssues?.items]
  );

  const isLoading = isAnalyticsLoading || isObservabilityLoading || isCostSummaryLoading;

  return (
    <Box data-testid="analytics-overview-tab">
      <ExecutiveKpiStrip
        positionTitle={t('analyticsDashboard.grain_positions')}
        runTitle={t('analyticsDashboard.grain_runs')}
        costTitle={t('analyticsDashboard.costs.sectionTitle')}
        positionKpis={positionKpis}
        runKpis={runKpis}
        costKpis={costKpis}
        isLoading={isLoading}
        hasPositionData={Boolean(summary)}
        hasRunData={Boolean(observability?.totals)}
        hasCostData={costHasData || isCostSummaryLoading}
      />

      {costHasData ? (
        <AnalyticsSectionCard
          title={t('analyticsDashboard.visual.costSnapshot')}
          subtitle={t('analyticsDashboard.costs.llmCostHint')}
        >
          {costWarnings.length > 0 ? (
            <Typography variant="caption" color="warning.main" display="block" sx={{ mb: 1 }}>
              {costWarnings[0]?.label}
              {costWarnings.length > 1 ? ` (+${costWarnings.length - 1})` : ''}
            </Typography>
          ) : null}
          <AnalyticsCostVisualSection costSummary={costSummary} isLoading={isCostSummaryLoading} compact />
        </AnalyticsSectionCard>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.qualitySnapshot')}>
            <AnalyticsChartCard title={t('analyticsDashboard.visual.autoVsManual')} data-testid="analytics-chart-auto-manual">
              <SegmentBarChart segments={autoManual} emptyText={emptyText} data-testid="analytics-chart-auto-manual-bars" />
            </AnalyticsChartCard>
            <Box sx={{ mt: 2 }}>
              <AnalyticsChartCard
                title={t('analyticsDashboard.visual.qualityIssues')}
                empty={!qualityChart.length}
                emptyText={emptyText}
                data-testid="analytics-chart-quality-issues"
              >
                <HorizontalBarChart data={qualityChart} emptyText={emptyText} data-testid="analytics-chart-quality-issues-bars" />
              </AnalyticsChartCard>
            </Box>
          </AnalyticsSectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.timeSnapshot')}>
            <AnalyticsChartCard
              title={t('analyticsDashboard.visual.processingTimeByInventory')}
              empty={!processingByInv.length}
              emptyText={emptyText}
              data-testid="analytics-chart-processing-inventory"
            >
              <HorizontalBarChart
                data={processingByInv}
                emptyText={emptyText}
                barColor="secondary.main"
                data-testid="analytics-chart-processing-inventory-bars"
              />
            </AnalyticsChartCard>
            <Box sx={{ mt: 2 }}>
              <TrendBars
                title={t('analyticsDashboard.time.trendTitle')}
                points={analytics.trends?.reviewed_results_over_time ?? []}
                emptyMessage={emptyText}
              />
            </Box>
          </AnalyticsSectionCard>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard
            title={t('analyticsDashboard.visual.providerSnapshot')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
          >
            <AnalyticsChartCard
              title={t('analyticsDashboard.visual.providerReliability')}
              empty={!providerReliability.length}
              emptyText={emptyText}
              data-testid="analytics-chart-provider-reliability"
            >
              <HorizontalBarChart
                data={providerReliability}
                emptyText={emptyText}
                data-testid="analytics-chart-provider-reliability-bars"
              />
            </AnalyticsChartCard>
          </AnalyticsSectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.aislesAttention')}>
            {!topAisles.length ? (
              <Typography variant="body2" color="text.secondary">
                {emptyText}
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {topAisles.map((row) => (
                  <Paper key={`${row.inventory_id}-${row.aisle_id}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Typography variant="body2" fontWeight={600}>
                      <MuiLink
                        component={RouterLink}
                        to={pathToAislePositions(row.inventory_id, row.aisle_id)}
                        underline="hover"
                      >
                        {row.aisle_code}
                      </MuiLink>
                      {' · '}
                      {row.inventory_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('analytics.column_pending')}: {row.needs_review_count}
                      {row.most_common_issue ? ` · ${row.most_common_issue}` : ''}
                    </Typography>
                  </Paper>
                ))}
              </Box>
            )}
          </AnalyticsSectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}
