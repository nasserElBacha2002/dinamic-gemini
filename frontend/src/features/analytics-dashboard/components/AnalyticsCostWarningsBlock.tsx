import { useTranslation } from 'react-i18next';
import { Alert, Box, Paper, Stack, Typography } from '@mui/material';
import type { AnalyticsCostWarningModel } from '../adapters/analyticsCostWarnings';

export interface AnalyticsCostWarningsBlockProps {
  warnings: readonly AnalyticsCostWarningModel[];
  compact?: boolean;
  /** Compact titled summary: first warnings + “+N más”. */
  summary?: boolean;
}

export function AnalyticsCostWarningsBlock({
  warnings,
  compact = false,
  summary = false,
}: AnalyticsCostWarningsBlockProps) {
  const { t } = useTranslation();

  if (!warnings.length) return null;

  if (summary) {
    const preview = warnings.slice(0, 2);
    const more = warnings.length - preview.length;
    return (
      <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }} data-testid="analytics-cost-warnings-summary">
        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          {t('analyticsDashboard.costs.warningsSummaryTitle')}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {t('analyticsDashboard.costs.warningsActiveCount', { count: warnings.length })}
        </Typography>
        <Box component="ul" sx={{ m: 0, pl: 2 }}>
          {preview.map((w) => (
            <Typography
              key={w.code}
              component="li"
              variant="caption"
              color={w.severity === 'warning' ? 'warning.main' : 'text.secondary'}
              data-testid={`analytics-cost-warning-${w.code}`}
            >
              {w.label}
            </Typography>
          ))}
        </Box>
        {more > 0 ? (
          <Typography variant="caption" color="text.secondary" data-testid="analytics-cost-warnings-more">
            {t('analyticsDashboard.visual.dataQualityMore', { count: more })}
          </Typography>
        ) : null}
      </Paper>
    );
  }

  if (compact) {
    return (
      <Stack spacing={0.5} sx={{ mb: 1.5 }} data-testid="analytics-cost-warnings">
        {warnings.map((w) => (
          <Typography
            key={w.code}
            variant="caption"
            color={w.severity === 'warning' ? 'warning.main' : 'text.secondary'}
            display="block"
            data-testid={`analytics-cost-warning-${w.code}`}
          >
            {w.label}
          </Typography>
        ))}
      </Stack>
    );
  }

  return (
    <Stack spacing={1} sx={{ mb: 2 }} data-testid="analytics-cost-warnings">
      {warnings.map((w) => (
        <Alert key={w.code} severity={w.severity} data-testid={`analytics-cost-warning-${w.code}`}>
          {w.label}
        </Alert>
      ))}
    </Stack>
  );
}
