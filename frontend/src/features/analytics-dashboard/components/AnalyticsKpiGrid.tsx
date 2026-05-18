import { Box, Skeleton, Typography } from '@mui/material';
import { KpiCard, KpiCardBand } from '../../../components/ui';
import type { DashboardKpiCardModel } from '../adapters/analyticsDashboardViewModel';

export interface AnalyticsKpiGridProps {
  cards: readonly DashboardKpiCardModel[];
  isLoading: boolean;
  hasData: boolean;
  skeletonCount?: number;
}

export function AnalyticsKpiGrid({ cards, isLoading, hasData, skeletonCount = 6 }: AnalyticsKpiGridProps) {
  return (
    <KpiCardBand variant="metricsGrid">
      {isLoading && !hasData
        ? Array.from({ length: skeletonCount }).map((_, i) => (
            <Skeleton key={`sk-${i}`} variant="rounded" height={100} sx={{ minWidth: 0 }} />
          ))
        : cards.map((k) => (
            <Box key={`${k.label}-${k.grainLabel ?? ''}`} sx={{ minWidth: 0, opacity: k.unavailable ? 0.85 : 1 }}>
              {k.grainLabel ? (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.25 }}>
                  {k.grainLabel}
                </Typography>
              ) : null}
              <KpiCard label={k.label} value={k.value} description={k.description} />
            </Box>
          ))}
    </KpiCardBand>
  );
}
