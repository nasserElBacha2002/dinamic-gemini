import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Grid, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { formatCostCell } from '../adapters/analyticsCostViewModel';
import {
  buildCaptureStatusChartData,
  buildCostByAisleChartData,
  buildCostByInventoryChartData,
  buildCostByProviderChartData,
} from '../adapters/analyticsChartDatasets';
import { AnalyticsChartCard } from './AnalyticsChartCard';
import { HorizontalBarChart } from './charts/HorizontalBarChart';

export interface AnalyticsCostVisualSectionProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  compact?: boolean;
}

export function AnalyticsCostVisualSection({
  costSummary,
  isLoading,
  compact = false,
}: AnalyticsCostVisualSectionProps) {
  const { t } = useTranslation();
  const emptyText = t('analyticsDashboard.visual.emptyChart');
  const loadingText = t('analyticsDashboard.visual.loadingChart');

  const byProvider = useMemo(() => buildCostByProviderChartData(costSummary), [costSummary]);
  const byInventory = useMemo(() => buildCostByInventoryChartData(costSummary), [costSummary]);
  const byAisle = useMemo(() => buildCostByAisleChartData(costSummary), [costSummary]);
  const captureStatus = useMemo(() => buildCaptureStatusChartData(costSummary, t), [costSummary, t]);

  const totals = costSummary?.totals;
  const unitEconomics = (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
        gap: 1.5,
        mb: compact ? 0 : 2,
      }}
      data-testid="analytics-unit-economics"
    >
      <Box sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t('analyticsDashboard.costs.costPerUnit')}
        </Typography>
        <Typography variant="subtitle1" fontWeight={700}>
          {formatCostCell(totals?.cost_per_counted_unit, 'costPerUnit', t)}
        </Typography>
      </Box>
      <Box sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t('analyticsDashboard.costs.totalQuantity')}
        </Typography>
        <Typography variant="subtitle1" fontWeight={700}>
          {formatCostCell(totals?.total_counted_quantity, 'quantity', t)}
        </Typography>
      </Box>
      <Box sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t('analyticsDashboard.costs.jobsWithCost')}
        </Typography>
        <Typography variant="subtitle1" fontWeight={700}>
          {formatCostCell(totals?.jobs_with_cost, 'integer', t)}
        </Typography>
      </Box>
      <Box sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t('analyticsDashboard.costs.jobsWithoutCost')}
        </Typography>
        <Typography variant="subtitle1" fontWeight={700}>
          {formatCostCell(totals?.jobs_without_cost, 'integer', t)}
        </Typography>
      </Box>
    </Box>
  );

  return (
    <Box data-testid="analytics-cost-visual-section">
      {!compact ? unitEconomics : null}
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.costByProviderModel')}
            subtitle={t('analyticsDashboard.visual.notARecommendation')}
            loading={isLoading}
            loadingText={loadingText}
            empty={!isLoading && !byProvider.length}
            emptyText={emptyText}
            data-testid="analytics-chart-cost-provider"
          >
            <HorizontalBarChart
              data={byProvider}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.visual.costByProviderModel')}
              data-testid="analytics-chart-cost-provider-bars"
            />
          </AnalyticsChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.captureStatusDistribution')}
            loading={isLoading}
            loadingText={loadingText}
            empty={!isLoading && !captureStatus.length}
            emptyText={emptyText}
            data-testid="analytics-chart-capture-status"
          >
            <HorizontalBarChart
              data={captureStatus}
              emptyText={emptyText}
              barColor="info.main"
              ariaLabel={t('analyticsDashboard.visual.captureStatusDistribution')}
              data-testid="analytics-chart-capture-status-bars"
            />
          </AnalyticsChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.topInventoriesByCost')}
            loading={isLoading}
            loadingText={loadingText}
            empty={!isLoading && !byInventory.length}
            emptyText={emptyText}
            data-testid="analytics-chart-cost-inventory"
          >
            <HorizontalBarChart
              data={byInventory}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.visual.topInventoriesByCost')}
              data-testid="analytics-chart-cost-inventory-bars"
            />
          </AnalyticsChartCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <AnalyticsChartCard
            title={t('analyticsDashboard.visual.topAislesByCost')}
            loading={isLoading}
            loadingText={loadingText}
            empty={!isLoading && !byAisle.length}
            emptyText={emptyText}
            data-testid="analytics-chart-cost-aisle"
          >
            <HorizontalBarChart
              data={byAisle}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.visual.topAislesByCost')}
              data-testid="analytics-chart-cost-aisle-bars"
            />
          </AnalyticsChartCard>
        </Grid>
      </Grid>
    </Box>
  );
}
