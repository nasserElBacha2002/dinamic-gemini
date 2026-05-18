import { Box, Skeleton, Typography } from '@mui/material';
import { KpiCard, KpiCardBand } from '../../../components/ui';
import type { DashboardKpiCardModel } from '../adapters/analyticsDashboardViewModel';

export interface ExecutiveKpiStripProps {
  positionTitle: string;
  runTitle: string;
  costTitle: string;
  positionKpis: readonly DashboardKpiCardModel[];
  runKpis: readonly DashboardKpiCardModel[];
  costKpis: readonly DashboardKpiCardModel[];
  isPositionLoading: boolean;
  isRunLoading: boolean;
  isCostLoading: boolean;
  hasPositionData: boolean;
  hasRunData: boolean;
  hasCostData: boolean;
}

function KpiGroup({
  title,
  cards,
  isLoading,
  hasData,
  skeletonCount,
}: {
  title: string;
  cards: readonly DashboardKpiCardModel[];
  isLoading: boolean;
  hasData: boolean;
  skeletonCount: number;
}) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1, letterSpacing: 0.6 }}>
        {title}
      </Typography>
      <KpiCardBand variant="metricsGrid">
        {isLoading && !hasData
          ? Array.from({ length: skeletonCount }).map((_, i) => (
              <Skeleton key={`sk-${title}-${i}`} variant="rounded" height={88} />
            ))
          : cards.map((k) => (
              <Box key={`${title}-${k.label}`} sx={{ minWidth: 0, opacity: k.unavailable ? 0.85 : 1 }}>
                <KpiCard label={k.label} value={k.value} description={k.description} />
              </Box>
            ))}
      </KpiCardBand>
    </Box>
  );
}

export function ExecutiveKpiStrip({
  positionTitle,
  runTitle,
  costTitle,
  positionKpis,
  runKpis,
  costKpis,
  isPositionLoading,
  isRunLoading,
  isCostLoading,
  hasPositionData,
  hasRunData,
  hasCostData,
}: ExecutiveKpiStripProps) {
  return (
    <Box
      data-testid="analytics-executive-kpi-strip"
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: 'repeat(3, minmax(0, 1fr))' },
        gap: 2,
        mb: 2,
      }}
    >
      <KpiGroup
        title={positionTitle}
        cards={positionKpis}
        isLoading={isPositionLoading}
        hasData={hasPositionData}
        skeletonCount={6}
      />
      <KpiGroup title={runTitle} cards={runKpis} isLoading={isRunLoading} hasData={hasRunData} skeletonCount={4} />
      <KpiGroup title={costTitle} cards={costKpis} isLoading={isCostLoading} hasData={hasCostData} skeletonCount={5} />
    </Box>
  );
}
