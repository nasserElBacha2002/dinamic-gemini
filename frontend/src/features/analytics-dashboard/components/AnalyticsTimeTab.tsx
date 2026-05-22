import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid } from '@mui/material';
import TrendBars from '../../analytics/components/TrendBars';
import { formatAvgProcessingMinutes, formatPct } from '../../analytics/adapters/metricsFormatters';
import {
  buildFastestInventoryInsight,
  buildProcessingTimeByInventoryData,
  buildProviderFailureRateChartData,
  buildSlowestInventoryInsight,
} from '../adapters/analyticsChartDatasets';
import { AnalyticsCompactKpiGrid } from './AnalyticsCompactKpiGrid';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import type { ObservabilityMetricsResponse } from '../../../api/types';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsTimeTabProps {
  analytics: AnalyticsBundle;
  observability: ObservabilityMetricsResponse | null | undefined;
  isLoading: boolean;
}

export function AnalyticsTimeTab({ analytics, observability, isLoading }: AnalyticsTimeTabProps) {
  const { t } = useTranslation();
  const { summary, trends, inventoryPerformance } = analytics;
  const invRows = inventoryPerformance?.items ?? [];

  const trendPoints = trends?.reviewed_results_over_time ?? [];
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const processingByInv = useMemo(() => buildProcessingTimeByInventoryData(invRows), [invRows]);
  const providerFailureChart = useMemo(
    () => buildProviderFailureRateChartData(observability),
    [observability]
  );
  const slowest = useMemo(() => buildSlowestInventoryInsight(invRows), [invRows]);
  const fastest = useMemo(() => buildFastestInventoryInsight(invRows), [invRows]);

  const avgSuccessRate = useMemo(() => {
    const rates = invRows
      .map((r) => r.processing_success_rate)
      .filter((v): v is number => v != null && Number.isFinite(v));
    if (!rates.length) return null;
    return rates.reduce((sum, v) => sum + v, 0) / rates.length;
  }, [invRows]);

  const overviewKpis = useMemo(
    () => [
      {
        id: 'avg-processing',
        label: t('analyticsDashboard.time.avgProcessing'),
        value: formatAvgProcessingMinutes(
          summary?.average_processing_time_minutes,
          summary?.average_processing_time_seconds
        ),
      },
      {
        id: 'slowest',
        label: t('analyticsDashboard.time.slowestInventory'),
        value: slowest ? `${slowest.name} (${slowest.minutes.toFixed(1)} min)` : '—',
      },
      {
        id: 'fastest',
        label: t('analyticsDashboard.time.fastestInventory'),
        value: fastest ? `${fastest.name} (${fastest.minutes.toFixed(1)} min)` : '—',
      },
      {
        id: 'success-rate',
        label: t('analyticsDashboard.time.avgSuccessRate'),
        value: avgSuccessRate != null ? formatPct(avgSuccessRate) : '—',
      },
    ],
    [t, summary, slowest, fastest, avgSuccessRate]
  );

  return (
    <Box data-testid="analytics-time-tab">
      <Box sx={{ mb: 2 }}>
        <AnalyticsSummaryPanel
          title={t('analyticsDashboard.time.overviewTitle')}
          isLoading={isLoading}
          loadingSkeletonHeight={88}
          data-testid="analytics-time-panel-overview"
        >
          <AnalyticsCompactKpiGrid items={overviewKpis} data-testid="analytics-time-overview-kpis" />
        </AnalyticsSummaryPanel>
      </Box>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.visual.processingTimeByInventory')}
            isLoading={isLoading}
            data-testid="analytics-time-panel-inventory"
          >
            <HorizontalBarChart
              data={processingByInv}
              emptyText={emptyText}
              barColor="secondary.main"
              ariaLabel={t('analyticsDashboard.visual.processingTimeByInventory')}
              data-testid="analytics-time-chart-inventory-bars"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.time.trendTitle')}
            subtitle={t('analyticsDashboard.grain_positions')}
            isLoading={isLoading}
            loadingSkeletonHeight={180}
            data-testid="analytics-time-panel-trend"
          >
            <Box data-testid="analytics-time-chart-trend" sx={{ minHeight: 180 }}>
              <TrendBars
                title={t('analyticsDashboard.time.trendTitle')}
                points={trendPoints}
                emptyMessage={emptyText}
                hideTitle
              />
            </Box>
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.time.providerFailureTitle')}
            subtitle={t('analyticsDashboard.grain_runs')}
            isLoading={isLoading}
            data-testid="analytics-time-panel-provider"
          >
            <HorizontalBarChart
              data={providerFailureChart}
              emptyText={emptyText}
              barColor="warning.main"
              ariaLabel={t('analyticsDashboard.time.providerFailureTitle')}
              data-testid="analytics-time-chart-provider-bars"
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
