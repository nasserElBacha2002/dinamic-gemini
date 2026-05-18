import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Grid, Link as MuiLink, Paper, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { pathToAislePositions, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { orderQualityRows } from '../../analytics/adapters/metricsViewModel';
import {
  buildPositionSummaryKpis,
  buildRunSummaryKpis,
  buildUnavailableGlobalCostKpis,
  hasUnidentifiedProductRate,
} from '../adapters/analyticsDashboardViewModel';
import {
  buildAutoVsManualSegments,
  buildProcessingTimeByInventoryData,
  buildProviderRunVolumeChartData,
  buildQualityIssueChartData,
  buildTopAislesAttention,
} from '../adapters/analyticsChartDatasets';
import { buildCostWarnings, buildOverviewCostKpis, hasCostData } from '../adapters/analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility, type AnalyticsDrilldownHandlers } from '../types';
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
    () => buildPositionSummaryKpis(summary, unidentified, t),
    [summary, unidentified, t]
  );
  const runKpis = useMemo(() => buildRunSummaryKpis(observability, t), [observability, t]);

  const costHasData = hasCostData(costSummary) && !isCostSummaryError;

  const costKpis = useMemo(() => {
    if (isCostSummaryLoading) {
      return [];
    }
    if (isCostSummaryError || !hasCostData(costSummary)) {
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
    () => buildTopAislesAttention(analytics.aisleIssues?.items ?? []),
    [analytics.aisleIssues?.items]
  );

  const showCostSection = (costHasData || isCostSummaryLoading) && !isCostSummaryError;

  return (
    <Box data-testid="analytics-overview-tab">
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
            <AnalyticsChartCard
              title={t('analyticsDashboard.visual.autoVsManual')}
              loading={isAnalyticsLoading}
              loadingText={loadingText}
              data-testid="analytics-chart-auto-manual"
            >
              <SegmentBarChart segments={autoManual} emptyText={emptyText} data-testid="analytics-chart-auto-manual-bars" />
            </AnalyticsChartCard>
            <Box sx={{ mt: 2 }}>
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
            </Box>
          </AnalyticsSectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.timeSnapshot')}>
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
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.visual.aislesAttention')}>
            {!topAisles.length ? (
              <Typography variant="body2" color="text.secondary">
                {emptyText}
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {topAisles.map((row) => {
                  const eligibility = getCompareEligibility(inventoryProcessingModeById.get(row.inventory_id));
                  const compareHref = eligibility.allowed
                    ? pathToInventoryAnalyticsCompareMany(row.inventory_id, { aisleId: row.aisle_id })
                    : '';
                  const compareTooltip = eligibility.allowed
                    ? ''
                    : t(compareEligibilityTooltipKey(eligibility.reason));

                  return (
                    <Paper
                      key={`${row.inventory_id}-${row.aisle_id}`}
                      variant="outlined"
                      sx={{ p: 1.5 }}
                      data-testid={`analytics-overview-aisle-${row.aisle_id}`}
                    >
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
                      <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => drilldown.onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
                          data-testid={`overview-aisle-drilldown-${row.aisle_id}`}
                        >
                          {t('analyticsDashboard.drilldown.openAnalytics')}
                        </Button>
                        <Tooltip title={compareTooltip}>
                          <span>
                            <Button
                              size="small"
                              variant="outlined"
                              component={eligibility.allowed ? RouterLink : 'button'}
                              to={eligibility.allowed ? compareHref : undefined}
                              disabled={!eligibility.allowed}
                              data-testid={`overview-aisle-compare-${row.aisle_id}`}
                            >
                              {t('analyticsDashboard.inventories.compareRuns')}
                            </Button>
                          </span>
                        </Tooltip>
                      </Box>
                    </Paper>
                  );
                })}
              </Box>
            )}
          </AnalyticsSectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}
