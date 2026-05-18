import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Stack } from '@mui/material';
import type { AnalyticsCostSummaryResponse, ObservabilityMetricsResponse } from '../../../api/types';
import { buildCostWarnings } from '../adapters/analyticsCostViewModel';

export interface AnalyticsDataQualitySummaryProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  observability: ObservabilityMetricsResponse | null | undefined;
  analyticsError?: boolean;
  observabilityError?: boolean;
  costSummaryError?: boolean;
}

export function AnalyticsDataQualitySummary({
  costSummary,
  observability,
  analyticsError,
  observabilityError,
  costSummaryError,
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

  return (
    <Stack spacing={1} sx={{ mb: 2 }} data-testid="analytics-data-quality-summary">
      <Alert severity="info" variant="outlined" sx={{ py: 0.5 }}>
        {t('analyticsDashboard.visual.dataQualitySummary')}
      </Alert>
      {items.map((item) => (
        <Alert key={item.id} severity={item.severity} data-testid={`analytics-dq-${item.id}`}>
          {item.message}
        </Alert>
      ))}
    </Stack>
  );
}
