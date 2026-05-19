import { Box, Grid, Typography } from '@mui/material';
import { DonutChart } from './charts/DonutChart';
import type { DonutSegment } from './charts/DonutChart';
import { AnalyticsMetricCard } from './base/AnalyticsMetricCard';

export interface AnalyticsQualityOverviewProps {
  chartTitle: string;
  donutSegments: readonly DonutSegment[];
  pendingReviewCount: number;
  processedPositionsCount: number;
  pendingLabel: string;
  processedLabel: string;
  emptyText: string;
  'data-testid'?: string;
}

export function AnalyticsQualityOverview({
  chartTitle,
  donutSegments,
  pendingReviewCount,
  processedPositionsCount,
  pendingLabel,
  processedLabel,
  emptyText,
  'data-testid': testId,
}: AnalyticsQualityOverviewProps) {
  return (
    <Box data-testid={testId}>
      <Grid container spacing={2} alignItems="stretch">
        <Grid item xs={12} md={7}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {chartTitle}
          </Typography>
          <DonutChart segments={donutSegments} emptyText={emptyText} data-testid={testId ? `${testId}-donut` : undefined} />
        </Grid>
        <Grid item xs={12} md={5}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, height: '100%' }}>
            <AnalyticsMetricCard
              label={pendingLabel}
              value={pendingReviewCount}
              size="regular"
              testId={testId ? `${testId}-kpi-pending` : undefined}
            />
            <AnalyticsMetricCard
              label={processedLabel}
              value={processedPositionsCount}
              size="regular"
              testId={testId ? `${testId}-kpi-processed` : undefined}
            />
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}
