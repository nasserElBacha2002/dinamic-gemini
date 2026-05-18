import { Alert, Stack, Typography } from '@mui/material';
import type { AnalyticsCostWarningModel } from '../adapters/analyticsCostWarnings';

export interface AnalyticsCostWarningsBlockProps {
  warnings: readonly AnalyticsCostWarningModel[];
  compact?: boolean;
}

export function AnalyticsCostWarningsBlock({ warnings, compact = false }: AnalyticsCostWarningsBlockProps) {
  if (!warnings.length) return null;

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
