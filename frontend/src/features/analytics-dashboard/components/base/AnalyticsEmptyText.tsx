import { Typography } from '@mui/material';

export interface AnalyticsEmptyTextProps {
  children: React.ReactNode;
  'data-testid'?: string;
}

export function AnalyticsEmptyText({ children, 'data-testid': testId }: AnalyticsEmptyTextProps) {
  return (
    <Typography variant="body2" color="text.secondary" data-testid={testId}>
      {children}
    </Typography>
  );
}
