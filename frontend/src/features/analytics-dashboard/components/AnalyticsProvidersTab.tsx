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
  Tooltip,
  Typography,
} from '@mui/material';
import type { AnalyticsCostSummaryResponse, ObservabilityMetricsResponse } from '../../../api/types';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import { buildCostByProviderChartData, buildProviderRunVolumeChartData } from '../adapters/analyticsChartDatasets';
import {
  buildCostWarnings,
  formatCostCell,
  formatProviderUnitCost,
} from '../adapters/analyticsCostViewModel';
import { AnalyticsChartCard } from './AnalyticsChartCard';
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
  const rows = observability?.by_provider_model ?? [];
  const costRows = costSummary?.by_provider_model ?? [];
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const runVolumeChart = useMemo(() => buildProviderRunVolumeChartData(observability), [observability]);
  const costChart = useMemo(() => buildCostByProviderChartData(costSummary), [costSummary]);

  return (
    <Box data-testid="analytics-providers-tab">
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.providerRunVolume')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
            empty={!runVolumeChart.length}
            emptyText={emptyText}
            data-testid="analytics-providers-chart-run-volume"
          >
            <HorizontalBarChart
              data={runVolumeChart}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.visual.providerRunVolume')}
              data-testid="analytics-providers-chart-run-volume-bars"
            />
          </AnalyticsChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.costByProviderModel')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
            empty={!costRows.length}
            emptyText={emptyText}
            data-testid="analytics-providers-chart-cost"
          >
            <HorizontalBarChart
              data={costChart}
              emptyText={emptyText}
              data-testid="analytics-providers-chart-cost-bars"
            />
          </AnalyticsChartCard>
        </Grid>
      </Grid>

      <AnalyticsSectionCard
        title={t('analyticsDashboard.providers.sectionTitle')}
        grainLabel={t('analyticsDashboard.grain_runs')}
        subtitle={t('analyticsDashboard.compare.notRecommendation')}
      >
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-providers-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colSucceeded')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colFailed')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colFailureRate')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, idx) => (
                <TableRow key={`${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}>
                  <TableCell>{row.provider_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell>{row.model_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell align="right">{row.runs_total}</TableCell>
                  <TableCell align="right">{row.runs_succeeded}</TableCell>
                  <TableCell align="right">{row.runs_failed}</TableCell>
                  <TableCell align="right">{pctLabel(row.failure_rate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
        {!rows.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('observability.metrics.empty')}
          </Typography>
        ) : null}
      </AnalyticsSectionCard>

      <AnalyticsSectionCard
        title={t('analyticsDashboard.costs.byProviderModelTitle')}
        subtitle={t('analyticsDashboard.compare.notRecommendation')}
      >
        {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {t('analyticsDashboard.costs.columnsContext')}
        </Typography>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-providers-cost-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.jobsWithCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {costRows.map((row, idx) => {
                const unit = formatProviderUnitCost(row.cost_per_counted_unit, t);
                return (
                  <TableRow key={`cost-${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}>
                    <TableCell>{row.provider_name ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell>{row.model_name ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell align="right">{row.jobs_total}</TableCell>
                    <TableCell align="right">{row.jobs_with_cost}</TableCell>
                    <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                    <TableCell align="right">
                      {unit.helper ? (
                        <Tooltip title={unit.helper}>
                          <span>{unit.display}</span>
                        </Tooltip>
                      ) : (
                        unit.display
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
        {!costRows.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('analyticsDashboard.costs.emptyNoJobs')}
          </Typography>
        ) : null}
      </AnalyticsSectionCard>
    </Box>
  );
}
