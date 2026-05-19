import type { ReactNode } from 'react';
import { Paper, Typography } from '@mui/material';

export interface AnalyticsSectionCardProps {
  title: string;
  subtitle?: string;
  grainLabel?: string;
  children: ReactNode;
}

export function AnalyticsSectionCard({ title, subtitle, grainLabel, children }: AnalyticsSectionCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2, minWidth: 0 }}>
      <Typography variant="subtitle1" gutterBottom>
        {title}
      </Typography>
      {grainLabel ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: subtitle ? 0.5 : 1 }}>
          {grainLabel}
        </Typography>
      ) : null}
      {subtitle ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {subtitle}
        </Typography>
      ) : null}
      {children}
    </Paper>
  );
}
