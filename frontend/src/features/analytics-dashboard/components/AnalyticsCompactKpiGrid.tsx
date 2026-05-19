import { Box } from '@mui/material';
import { AnalyticsMetricCard } from './base/AnalyticsMetricCard';

export interface CompactKpiItem {
  id: string;
  label: string;
  value: string;
}

export interface AnalyticsCompactKpiGridProps {
  items: readonly CompactKpiItem[];
  'data-testid'?: string;
}

export function AnalyticsCompactKpiGrid({ items, 'data-testid': testId }: AnalyticsCompactKpiGridProps) {
  if (!items.length) return null;

  return (
    <Box
      data-testid={testId}
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: `repeat(${Math.min(items.length, 4)}, minmax(0, 1fr))` },
        gap: 1.5,
      }}
    >
      {items.map((item) => (
        <AnalyticsMetricCard
          key={item.id}
          label={item.label}
          value={item.value}
          size="compact"
          testId={testId ? `${testId}-${item.id}` : undefined}
        />
      ))}
    </Box>
  );
}
