import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';

type ProviderRow = ObservabilityMetricsResponse['by_provider_model'][number];

export interface AnalyticsProviderComparisonCardsProps {
  rows: readonly ProviderRow[];
  emptyText: string;
}

function pctLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

export function AnalyticsProviderComparisonCards({ rows, emptyText }: AnalyticsProviderComparisonCardsProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-providers-comparison-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box
      data-testid="analytics-providers-comparison-cards"
      sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}
    >
      {rows.map((row, idx) => (
        <Paper
          key={`${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}
          variant="outlined"
          data-testid={`analytics-provider-card-${idx}`}
          sx={{ p: 1.25 }}
        >
          <Typography variant="body2" fontWeight={700} gutterBottom>
            {row.provider_name ?? t('observability.metrics.unknownId')} / {row.model_name ?? t('observability.metrics.unknownId')}
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 0.75 }}>
            <Typography variant="caption" color="text.secondary">
              {t('observability.metrics.colRuns')}: {row.runs_total}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('observability.metrics.colSucceeded')}: {row.runs_succeeded}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('observability.metrics.colFailed')}: {row.runs_failed}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.providers.observedFailureRate')}: {pctLabel(row.failure_rate)}
            </Typography>
          </Box>
        </Paper>
      ))}
    </Box>
  );
}
