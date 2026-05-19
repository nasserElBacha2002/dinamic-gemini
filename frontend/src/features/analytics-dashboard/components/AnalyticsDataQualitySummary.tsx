import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse, ObservabilityMetricsResponse } from '../../../api/types';
import { buildCostWarnings } from '../adapters/analyticsCostViewModel';

export interface AnalyticsDataQualitySummaryProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  observability: ObservabilityMetricsResponse | null | undefined;
  analyticsError?: boolean;
  observabilityError?: boolean;
  costSummaryError?: boolean;
  maxVisibleItems?: number;
}

export function AnalyticsDataQualitySummary({
  costSummary,
  observability,
  analyticsError,
  observabilityError,
  costSummaryError,
  maxVisibleItems = 3,
}: AnalyticsDataQualitySummaryProps) {
  const { t } = useTranslation();
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);

  const items: { id: string; severity: 'info' | 'warning'; message: string }[] = [];

  if (analyticsError) {
    items.push({
      id: 'analytics-failed',
      severity: 'warning',
      message: t('analyticsDashboard.partial.analyticsFailed'),
    });
  }
  if (observabilityError) {
    items.push({
      id: 'observability-failed',
      severity: 'warning',
      message: t('analyticsDashboard.partial.observabilityFailed'),
    });
  }
  if (costSummaryError) {
    items.push({
      id: 'cost-failed',
      severity: 'warning',
      message: t('analyticsDashboard.partial.costFailed'),
    });
  }
  if ((observability?.data_quality?.jobs_without_audit_snapshot ?? 0) > 0) {
    items.push({
      id: 'obs-no-snapshot',
      severity: 'warning',
      message: t('analyticsDashboard.partial.observabilityNoSnapshot'),
    });
  }
  for (const w of costWarnings) {
    items.push({ id: w.code, severity: w.severity, message: w.label });
  }

  if (!items.length) return null;

  const visibleItems = items.slice(0, maxVisibleItems);
  const hiddenCount = items.length - visibleItems.length;

  return (
    <Alert severity="warning" variant="outlined" sx={{ mb: 2 }} data-testid="analytics-data-quality-summary">
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {t('analyticsDashboard.visual.dataQualityTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('analyticsDashboard.visual.dataQualityWarningsActive', { count: items.length })}
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {visibleItems.map((item) => (
          <Typography key={item.id} component="li" variant="body2" data-testid={`analytics-dq-${item.id}`}>
            {item.message}
          </Typography>
        ))}
      </Box>
      {hiddenCount > 0 ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {t('analyticsDashboard.visual.dataQualityMore', { count: hiddenCount })}
        </Typography>
      ) : null}
    </Alert>
  );
}
