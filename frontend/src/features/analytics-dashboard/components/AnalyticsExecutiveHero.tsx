import { Box, Skeleton } from '@mui/material';
import type { HeroKpiModel } from '../adapters/analyticsDashboardViewModel';
import { AnalyticsMetricCard } from './base/AnalyticsMetricCard';

export interface AnalyticsExecutiveHeroProps {
  kpis: readonly HeroKpiModel[];
  isLoading: boolean;
  hasData: boolean;
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
              <AnalyticsMetricCard
                key={kpi.id}
                label={kpi.label}
                value={kpi.value}
                size="hero"
                tone={kpi.unavailable ? 'disabled' : 'default'}
                testId={`analytics-hero-kpi-${kpi.id}`}
              />
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
              <AnalyticsMetricCard
                key={kpi.id}
                label={kpi.label}
                value={kpi.value}
                size="compact"
                tone={kpi.unavailable ? 'disabled' : 'default'}
                testId={`analytics-hero-kpi-${kpi.id}`}
              />
            ))}
          </Box>
        </>
      )}
    </Box>
  );
}
