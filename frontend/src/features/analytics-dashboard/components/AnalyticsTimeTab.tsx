import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid } from '@mui/material';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import TrendBars from '../../analytics/components/TrendBars';
import { formatAvgProcessingMinutes, formatPct } from '../../analytics/adapters/metricsFormatters';
import { buildProcessingTimeByInventoryData } from '../adapters/analyticsChartDatasets';
import { AnalyticsChartCard } from './AnalyticsChartCard';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
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

  const trendPoints = trends?.reviewed_results_over_time ?? [];
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const loadingText = t('analyticsDashboard.visual.loadingChart');
  const processingByInv = useMemo(
    () => buildProcessingTimeByInventoryData(inventoryPerformance?.items ?? []),
    [inventoryPerformance?.items]
  );

  return (
    <Box data-testid="analytics-time-tab">
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.processingTimeByInventory')}
            loading={isLoading}
            loadingText={loadingText}
            empty={!isLoading && !processingByInv.length}
            emptyText={emptyText}
            data-testid="analytics-time-chart-inventory"
          >
            <HorizontalBarChart
              data={processingByInv}
              emptyText={emptyText}
              barColor="secondary.main"
              ariaLabel={t('analyticsDashboard.visual.processingTimeByInventory')}
              data-testid="analytics-time-chart-inventory-bars"
            />
          </AnalyticsChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsSectionCard title={t('analyticsDashboard.time.trendTitle')} grainLabel={t('analyticsDashboard.grain_positions')}>
            <TrendBars title={t('analyticsDashboard.time.trendTitle')} points={trendPoints} emptyMessage={emptyText} />
          </AnalyticsSectionCard>
        </Grid>
      </Grid>

      <AnalyticsSectionCard
        title={t('analyticsDashboard.time.avgProcessing')}
        grainLabel={t('analyticsDashboard.grain_positions')}
      >
        <Typography variant="h5" data-testid="analytics-avg-processing">
          {formatAvgProcessingMinutes(summary?.average_processing_time_minutes, summary?.average_processing_time_seconds)}
        </Typography>
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.time.byInventory')} grainLabel={t('analyticsDashboard.grain_positions')}>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-time-inventories-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('analytics.column_inventory')}</TableCell>
                <TableCell align="right">{t('analytics.column_avg_processing')}</TableCell>
                <TableCell align="right">{t('analytics.column_job_success')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(inventoryPerformance?.items ?? []).map((row) => (
                <TableRow key={row.inventory_id}>
                  <TableCell>{row.inventory_name}</TableCell>
                  <TableCell align="right">
                    {formatAvgProcessingMinutes(row.average_processing_time_minutes, null)}
                  </TableCell>
                  <TableCell align="right">{formatPct(row.processing_success_rate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>

      <AnalyticsSectionCard
        title={t('analyticsDashboard.time.byProviderModel')}
        grainLabel={t('analyticsDashboard.grain_runs')}
      >
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-time-provider-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colFailureRate')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(observability?.by_provider_model ?? []).map((row, idx) => (
                <TableRow key={`${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}>
                  <TableCell>{row.provider_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell>{row.model_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell align="right">{row.runs_total}</TableCell>
                  <TableCell align="right">
                    {row.failure_rate != null ? `${(row.failure_rate * 100).toFixed(1)} %` : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>
    </Box>
  );
}
