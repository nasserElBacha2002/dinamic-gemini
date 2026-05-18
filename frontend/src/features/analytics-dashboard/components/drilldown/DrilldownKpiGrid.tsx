import { Box, Skeleton } from '@mui/material';
import { KpiCard, KpiCardBand } from '../../../../components/ui';
import type { MetricCardModel } from '../../adapters/analyticsCostViewModel';

export interface DrilldownKpiGridProps {
  cards: readonly MetricCardModel[];
  isLoading?: boolean;
  'data-testid'?: string;
}

export function DrilldownKpiGrid({ cards, isLoading, 'data-testid': testId }: DrilldownKpiGridProps) {
  return (
    <Box data-testid={testId}>
      <KpiCardBand variant="metricsGrid">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={`drilldown-sk-${i}`} variant="rounded" height={88} />
            ))
          : cards.map((k) => (
              <Box key={k.label} sx={{ minWidth: 0, opacity: k.unavailable ? 0.85 : 1 }}>
                <KpiCard label={k.label} value={k.value} description={k.description} />
              </Box>
            ))}
      </KpiCardBand>
    </Box>
  );
}
