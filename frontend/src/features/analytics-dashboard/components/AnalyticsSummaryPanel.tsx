import type { ReactNode } from 'react';
import { Box, Button, Paper, Skeleton, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export interface AnalyticsSummaryPanelProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  ctaLabel?: string;
  ctaHref?: string;
  isLoading?: boolean;
  loadingSkeletonHeight?: number;
  'data-testid'?: string;
}

export function AnalyticsSummaryPanel({
  title,
  subtitle,
  children,
  ctaLabel,
  ctaHref,
  isLoading = false,
  loadingSkeletonHeight = 140,
  'data-testid': testId,
}: AnalyticsSummaryPanelProps) {
  return (
    <Paper
      variant="outlined"
      data-testid={testId}
      sx={{
        p: 2,
        minHeight: 220,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
      }}
    >
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {title}
      </Typography>
      {subtitle ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          {subtitle}
        </Typography>
      ) : null}
      <Box sx={{ flex: 1, minHeight: loadingSkeletonHeight, mb: ctaLabel ? 1.5 : 0 }}>
        {isLoading ? <Skeleton variant="rounded" height={loadingSkeletonHeight} /> : children}
      </Box>
      {ctaLabel && ctaHref ? (
        <Button
          component={RouterLink}
          to={ctaHref}
          size="small"
          variant="text"
          sx={{ alignSelf: 'flex-start', px: 0 }}
          data-testid={testId ? `${testId}-cta` : undefined}
        >
          {ctaLabel}
        </Button>
      ) : null}
    </Paper>
  );
}
