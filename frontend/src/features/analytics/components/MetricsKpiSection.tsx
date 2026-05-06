import type { ReactNode } from 'react';
import { Box, Skeleton } from '@mui/material';
import { KpiCard } from '../../../components/ui';

export interface MetricsKpiCardView {
  label: string;
  value: ReactNode;
  description?: string;
}

export interface MetricsKpiSectionProps {
  cards: readonly MetricsKpiCardView[];
  isLoading: boolean;
  hasSummary: boolean;
  skeletonCount: number;
}

export function MetricsKpiSection({ cards, isLoading, hasSummary, skeletonCount }: MetricsKpiSectionProps) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: 'minmax(0, 1fr)',
          sm: 'repeat(2, minmax(0, 1fr))',
          md: 'repeat(3, minmax(0, 1fr))',
        },
        gap: 2,
        mb: 2,
        minWidth: 0,
        width: '100%',
      }}
    >
      {isLoading && !hasSummary
        ? Array.from({ length: skeletonCount }).map((_, i) => (
            <Skeleton key={`sk-${i}`} variant="rounded" height={100} sx={{ minWidth: 0 }} />
          ))
        : cards.map((k) => (
            <Box key={k.label} sx={{ minWidth: 0 }}>
              <KpiCard label={k.label} value={k.value} description={k.description} />
            </Box>
          ))}
    </Box>
  );
}
