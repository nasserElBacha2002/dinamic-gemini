import type { ReactNode } from 'react';
import { Paper, type PaperProps } from '@mui/material';

export interface AnalyticsCardProps extends Omit<PaperProps, 'title'> {
  children: ReactNode;
  'data-testid'?: string;
}

export function AnalyticsCard({ children, 'data-testid': testId, sx, ...rest }: AnalyticsCardProps) {
  return (
    <Paper variant="outlined" data-testid={testId} sx={{ p: 1.5, ...sx }} {...rest}>
      {children}
    </Paper>
  );
}
