import type { ReactNode } from 'react';
import { Box, Typography } from '@mui/material';

export interface AnalyticsMetadataItem {
  id: string;
  label: string;
  value: ReactNode;
  fullWidth?: boolean;
  tone?: 'default' | 'warning' | 'disabled';
  testId?: string;
}

export interface AnalyticsMetadataGridProps {
  items: readonly AnalyticsMetadataItem[];
  columns?: 1 | 2 | 3;
  testId?: string;
}

export function AnalyticsMetadataGrid({ items, columns = 2, testId }: AnalyticsMetadataGridProps) {
  if (!items.length) return null;

  return (
    <Box
      data-testid={testId}
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gap: 0.75,
      }}
    >
      {items.map((item) => (
        <Typography
          key={item.id}
          variant="caption"
          color={
            item.tone === 'warning' ? 'warning.main' : item.tone === 'disabled' ? 'text.disabled' : 'text.secondary'
          }
          sx={item.fullWidth ? { gridColumn: '1 / -1' } : undefined}
          data-testid={item.testId}
        >
          {item.label}: {item.value}
        </Typography>
      ))}
    </Box>
  );
}
