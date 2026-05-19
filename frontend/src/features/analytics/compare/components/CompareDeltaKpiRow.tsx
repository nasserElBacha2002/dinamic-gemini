import { Box, Paper, Typography } from '@mui/material';
import type { CompareDeltaKpi, CompareTargetDeltaRowModel } from '../compareBenchmarkViewModel';

type CompareDeltaKpiRowProps = {
  rows: CompareTargetDeltaRowModel[];
  compact?: boolean;
};

function toneColor(tone: CompareDeltaKpi['tone']): string {
  if (tone === 'positive') return 'success.main';
  if (tone === 'negative') return 'error.main';
  if (tone === 'warning') return 'warning.main';
  return 'text.primary';
}

export default function CompareDeltaKpiRow({ rows, compact = false }: CompareDeltaKpiRowProps) {
  return (
    <Box data-testid="compare-benchmark-delta-kpis" sx={{ display: 'grid', gap: compact ? 1.5 : 2 }}>
      {rows.map((row) => (
        <Paper key={row.targetJobId} variant="outlined" sx={{ p: compact ? 1.5 : 2 }}>
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            {row.title}
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gap: 1,
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))' },
            }}
          >
            {row.kpis.map((kpi) => (
              <Box key={kpi.id} data-testid={`compare-delta-kpi-${row.targetJobId}-${kpi.id}`}>
                <Typography variant="caption" color="text.secondary" display="block">
                  {kpi.label}
                </Typography>
                <Typography variant="body2" fontWeight={600} sx={{ color: toneColor(kpi.tone) }}>
                  {kpi.value}
                </Typography>
                {kpi.helper ? (
                  <Typography variant="caption" color="text.secondary" display="block">
                    {kpi.helper}
                  </Typography>
                ) : null}
              </Box>
            ))}
          </Box>
        </Paper>
      ))}
    </Box>
  );
}
