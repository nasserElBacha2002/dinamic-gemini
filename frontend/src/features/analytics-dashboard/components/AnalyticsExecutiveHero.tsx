import { Box, Paper, Skeleton, Typography } from '@mui/material';
import type { HeroKpiModel } from '../adapters/analyticsDashboardViewModel';

export interface AnalyticsExecutiveHeroProps {
  kpis: readonly HeroKpiModel[];
  isLoading: boolean;
  hasData: boolean;
}

function HeroKpiCard({ kpi }: { kpi: HeroKpiModel }) {
  const isPrimary = kpi.tier === 'primary';
  return (
    <Paper
      variant="outlined"
      sx={{
        p: isPrimary ? 2 : 1.5,
        minHeight: isPrimary ? 96 : 72,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        opacity: kpi.unavailable ? 0.85 : 1,
      }}
      data-testid={`analytics-hero-kpi-${kpi.id}`}
    >
      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, lineHeight: 1.3 }}>
        {kpi.label}
      </Typography>
      <Typography
        variant={isPrimary ? 'h5' : 'subtitle1'}
        component="p"
        fontWeight={700}
        sx={{ lineHeight: 1.2, wordBreak: 'break-word' }}
      >
        {kpi.value}
      </Typography>
    </Paper>
  );
}

export function AnalyticsExecutiveHero({ kpis, isLoading, hasData }: AnalyticsExecutiveHeroProps) {
  const primary = kpis.filter((k) => k.tier === 'primary');
  const secondary = kpis.filter((k) => k.tier === 'secondary');

  return (
    <Box data-testid="analytics-executive-hero" sx={{ mb: 3 }}>
      {isLoading && !hasData ? (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
            gap: 1.5,
          }}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={`hero-sk-${i}`} variant="rounded" height={i < 3 ? 96 : 72} />
          ))}
        </Box>
      ) : (
        <>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
              gap: 1.5,
              mb: 1.5,
            }}
            data-testid="analytics-hero-primary-row"
          >
            {primary.map((kpi) => (
              <HeroKpiCard key={kpi.id} kpi={kpi} />
            ))}
          </Box>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
              gap: 1.5,
            }}
            data-testid="analytics-hero-secondary-row"
          >
            {secondary.map((kpi) => (
              <HeroKpiCard key={kpi.id} kpi={kpi} />
            ))}
          </Box>
        </>
      )}
    </Box>
  );
}
