import { Box, Skeleton, Typography } from '@mui/material';
import { KpiCard, KpiCardBand } from '../../../components/ui';
import type { DashboardKpiCardModel } from '../adapters/analyticsDashboardViewModel';
import { EXECUTIVE_SUMMARY_KPI_LIMIT } from '../adapters/analyticsDashboardViewModel';

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

const EXECUTIVE_GRID_SX = {
  gridTemplateColumns: {
    xs: 'repeat(2, minmax(0, 1fr))',
    md: `repeat(${EXECUTIVE_SUMMARY_KPI_LIMIT}, minmax(0, 1fr))`,
  },
  gap: 1.5,
  mb: 0,
} as const;

function KpiGroup({
  groupId,
  title,
  cards,
  isLoading,
  hasData,
}: {
  groupId: string;
  title: string;
  cards: readonly DashboardKpiCardModel[];
  isLoading: boolean;
  hasData: boolean;
}) {
  return (
    <Box sx={{ minWidth: 0 }} data-testid={`analytics-executive-kpi-group-${groupId}`}>
      <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1, letterSpacing: 0.6 }}>
        {title}
      </Typography>
      <KpiCardBand variant="metricsGrid" sx={EXECUTIVE_GRID_SX}>
        {isLoading && !hasData
          ? Array.from({ length: EXECUTIVE_SUMMARY_KPI_LIMIT }).map((_, i) => (
              <Skeleton key={`sk-${title}-${i}`} variant="rounded" height={96} />
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
        mb: 3,
        p: { xs: 1.5, md: 2 },
        border: 1,
        borderColor: 'divider',
        borderRadius: 2,
        bgcolor: 'background.paper',
      }}
    >
      <KpiGroup
        groupId="positions"
        title={positionTitle}
        cards={positionKpis}
        isLoading={isPositionLoading}
        hasData={hasPositionData}
      />
      <KpiGroup
        groupId="runs"
        title={runTitle}
        cards={runKpis}
        isLoading={isRunLoading}
        hasData={hasRunData}
      />
      <KpiGroup
        groupId="cost"
        title={costTitle}
        cards={costKpis}
        isLoading={isCostLoading}
        hasData={hasCostData}
      />
    </Box>
  );
}
