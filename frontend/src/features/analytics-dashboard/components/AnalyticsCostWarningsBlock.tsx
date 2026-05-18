import { Alert, Stack } from '@mui/material';
import type { AnalyticsCostWarningModel } from '../adapters/analyticsCostWarnings';

export interface AnalyticsCostWarningsBlockProps {
  warnings: readonly AnalyticsCostWarningModel[];
}

export function AnalyticsCostWarningsBlock({ warnings }: AnalyticsCostWarningsBlockProps) {
  if (!warnings.length) return null;
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
