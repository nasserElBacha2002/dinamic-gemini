import type { ReactNode } from 'react';
import { Paper, Skeleton, Typography } from '@mui/material';

export interface AnalyticsChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  empty?: boolean;
  emptyText?: string;
  loading?: boolean;
  loadingText?: string;
  'data-testid'?: string;
}

export function AnalyticsChartCard({
  title,
  subtitle,
  children,
  empty,
  emptyText,
  loading,
  loadingText,
  'data-testid': testId,
}: AnalyticsChartCardProps) {
  return (
    <Paper
      variant="outlined"
      data-testid={testId}
      sx={{
        p: 2,
        height: '100%',
        minWidth: 0,
        bgcolor: 'background.paper',
        borderColor: 'divider',
      }}
    >
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {title}
      </Typography>
      {subtitle ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          {subtitle}
        </Typography>
      ) : null}
      {loading ? (
        <>
          {loadingText ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid={testId ? `${testId}-loading` : undefined}
            >
              {loadingText}
            </Typography>
          ) : null}
          <Skeleton variant="rounded" height={120} sx={{ mt: loadingText ? 1 : 0 }} />
        </>
      ) : empty && emptyText ? (
        <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
          {emptyText}
        </Typography>
      ) : (
        children
      )}
    </Paper>
  );
}
