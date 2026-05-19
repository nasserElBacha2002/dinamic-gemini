import { Box, Grid, Paper, Typography } from '@mui/material';
import { DonutChart } from './charts/DonutChart';
import type { DonutSegment } from './charts/DonutChart';

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

function QualityKpiCard({ label, value, testId }: { label: string; value: number; testId?: string }) {
  return (
    <Paper variant="outlined" data-testid={testId} sx={{ p: 1.5, flex: 1, minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="h6" fontWeight={700}>
        {value}
      </Typography>
    </Paper>
  );
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
            <QualityKpiCard
              label={pendingLabel}
              value={pendingReviewCount}
              testId={testId ? `${testId}-kpi-pending` : undefined}
            />
            <QualityKpiCard
              label={processedLabel}
              value={processedPositionsCount}
              testId={testId ? `${testId}-kpi-processed` : undefined}
            />
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
}
