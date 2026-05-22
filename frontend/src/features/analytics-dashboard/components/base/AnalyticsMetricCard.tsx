import type { ReactNode } from 'react';
import { Skeleton, Typography } from '@mui/material';
import { AnalyticsCard } from './AnalyticsCard';

export interface AnalyticsMetricCardProps {
  label: string;
  value: ReactNode;
  description?: ReactNode;
  size?: 'compact' | 'regular' | 'hero';
  tone?: 'default' | 'info' | 'warning' | 'disabled';
  loading?: boolean;
  testId?: string;
}

const valueVariant = {
  compact: 'subtitle1' as const,
  regular: 'h6' as const,
  hero: 'h5' as const,
};

const minHeights = {
  compact: 72,
  regular: 84,
  hero: 96,
};

export function AnalyticsMetricCard({
  label,
  value,
  description,
  size = 'regular',
  tone = 'default',
  loading = false,
  testId,
}: AnalyticsMetricCardProps) {
  const disabled = tone === 'disabled';

  return (
    <AnalyticsCard
      data-testid={testId}
      sx={{
        minHeight: minHeights[size],
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        opacity: disabled ? 0.85 : 1,
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, lineHeight: 1.3 }} noWrap title={label}>
        {label}
      </Typography>
      {loading ? (
        <Skeleton variant="text" width="60%" height={size === 'hero' ? 32 : 24} />
      ) : (
        <Typography
          variant={valueVariant[size]}
          component="p"
          fontWeight={700}
          color={tone === 'warning' ? 'warning.main' : undefined}
          sx={{ lineHeight: 1.2, wordBreak: 'break-word' }}
        >
          {value}
        </Typography>
      )}
      {description ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
          {description}
        </Typography>
      ) : null}
    </AnalyticsCard>
  );
}
