import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse, ObservabilityMetricsResponse } from '../../../api/types';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import {
  buildCostByProviderChartData,
  buildProviderCostDonutSegments,
  buildProviderFailureRateChartData,
  buildProviderRunVolumeChartData,
  buildTopProviderInsight,
  CHART_TOP_N,
} from '../adapters/analyticsChartDatasets';
import { buildCostWarnings } from '../adapters/analyticsCostViewModel';
import { formatLlmCostAmount } from '../adapters/analyticsCostFormatters';
import { AnalyticsCompactKpiGrid } from './AnalyticsCompactKpiGrid';
import { buildProviderComparisonCardItems } from '../adapters/entityRankingViewModels';
import { AnalyticsEntityRankingCards } from './rankings/AnalyticsEntityRankingCards';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { DonutChart } from './charts/DonutChart';
import { HorizontalBarChart } from './charts/HorizontalBarChart';

export interface AnalyticsProvidersTabProps {
  observability: ObservabilityMetricsResponse | null | undefined;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
}

function pctLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

export function AnalyticsProvidersTab({ observability, costSummary }: AnalyticsProvidersTabProps) {
  const { t } = useTranslation();
  const obsRows = observability?.by_provider_model ?? [];
  const costRows = costSummary?.by_provider_model ?? [];
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const runVolumeChart = useMemo(() => buildProviderRunVolumeChartData(observability), [observability]);
  const costChart = useMemo(() => buildCostByProviderChartData(costSummary), [costSummary]);
  const costDonut = useMemo(() => buildProviderCostDonutSegments(costSummary), [costSummary]);
  const failureChart = useMemo(() => buildProviderFailureRateChartData(observability), [observability]);
  const topProvider = useMemo(() => buildTopProviderInsight(observability), [observability]);

  const topCostRow = useMemo(() => {
    return [...costRows]
      .filter((r) => r.total_cost != null && Number.isFinite(r.total_cost) && r.total_cost > 0)
      .sort((a, b) => (b.total_cost ?? 0) - (a.total_cost ?? 0))[0];
  }, [costRows]);

  const lowestFailureRow = useMemo(() => {
    return [...obsRows]
      .filter((r) => r.runs_total > 0 && r.failure_rate != null && Number.isFinite(r.failure_rate))
      .sort((a, b) => (a.failure_rate ?? 0) - (b.failure_rate ?? 0))[0];
  }, [obsRows]);

  const comparisonRows = useMemo(
    () =>
      [...obsRows]
        .sort((a, b) => b.runs_total - a.runs_total)
        .slice(0, CHART_TOP_N),
    [obsRows]
  );
  const comparisonItems = useMemo(
    () => buildProviderComparisonCardItems(comparisonRows, t),
    [comparisonRows, t]
  );

  const totals = costSummary?.totals;
  const overviewKpis = useMemo(
    () => [
      {
        id: 'top-runs',
        label: t('analyticsDashboard.providers.topByRuns'),
        value: topProvider ? `${topProvider.label} (${topProvider.runs})` : '—',
      },
      {
        id: 'top-cost',
        label: t('analyticsDashboard.providers.topByCost'),
        value: topCostRow
          ? `${topCostRow.provider_name ?? '—'} / ${topCostRow.model_name ?? '—'} (${formatLlmCostAmount(topCostRow.total_cost!)})`
          : '—',
      },
      {
        id: 'low-failure',
        label: t('analyticsDashboard.providers.lowestFailureRate'),
        value: lowestFailureRow
          ? `${lowestFailureRow.provider_name ?? '—'} / ${lowestFailureRow.model_name ?? '—'} (${pctLabel(lowestFailureRow.failure_rate)})`
          : '—',
      },
      {
        id: 'jobs-cost',
        label: t('analyticsDashboard.providers.jobsCostSplit'),
        value:
          totals != null
            ? `${totals.jobs_with_cost ?? 0} / ${totals.jobs_without_cost ?? 0}`
            : '—',
      },
    ],
    [t, topProvider, topCostRow, lowestFailureRow, totals]
  );

  return (
    <Box data-testid="analytics-providers-tab">
      <Box sx={{ mb: 2 }}>
        <AnalyticsSummaryPanel
          title={t('analyticsDashboard.providers.overviewTitle')}
          subtitle={t('analyticsDashboard.visual.notARecommendation')}
          data-testid="analytics-providers-panel-overview"
        >
          <AnalyticsCompactKpiGrid items={overviewKpis} data-testid="analytics-providers-overview-kpis" />
        </AnalyticsSummaryPanel>
      </Box>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.providers.activityTitle')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
            data-testid="analytics-providers-panel-activity"
          >
            <HorizontalBarChart
              data={runVolumeChart}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.visual.providerRunVolume')}
              data-testid="analytics-providers-chart-run-volume-bars"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.providers.costTitle')}
            subtitle={t('analyticsDashboard.compare.notRecommendation')}
            data-testid="analytics-providers-panel-cost"
          >
            {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}
            <HorizontalBarChart
              data={costChart}
              emptyText={emptyText}
              data-testid="analytics-providers-chart-cost-bars"
            />
            {costDonut.length > 0 ? (
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                  {t('analyticsDashboard.providers.costDistributionTitle')}
                </Typography>
                <DonutChart
                  segments={costDonut}
                  emptyText={emptyText}
                  data-testid="analytics-providers-cost-donut"
                />
              </Box>
            ) : null}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.providers.reliabilityTitle')}
            subtitle={t('analyticsDashboard.compare.notRecommendation')}
            data-testid="analytics-providers-panel-reliability"
          >
            <Box sx={{ mb: 2 }}>
              <HorizontalBarChart
                data={failureChart}
                emptyText={emptyText}
                barColor="warning.main"
                ariaLabel={t('analyticsDashboard.providers.observedFailureRate')}
                data-testid="analytics-providers-chart-failure-bars"
              />
            </Box>
            <AnalyticsEntityRankingCards
              items={comparisonItems}
              emptyText={emptyText}
              testId="analytics-providers-comparison-cards"
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
