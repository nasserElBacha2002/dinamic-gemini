import { Box, Typography } from '@mui/material';
import type { BarChartDatum } from '../../adapters/analyticsChartDatasets';

export interface HorizontalBarChartProps {
  data: readonly BarChartDatum[];
  emptyText: string;
  'data-testid'?: string;
  barColor?: string;
}

export function HorizontalBarChart({
  data,
  emptyText,
  'data-testid': testId,
  barColor = 'primary.main',
}: HorizontalBarChartProps) {
  if (!data.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
        {emptyText}
      </Typography>
    );
  }

  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <Box data-testid={testId} sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {data.map((item) => {
        const widthPct = Math.max(4, (item.value / max) * 100);
        return (
          <Box key={item.id} sx={{ minWidth: 0 }} data-testid={testId ? `${testId}-row-${item.id}` : undefined}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, mb: 0.35 }}>
              <Typography variant="caption" color="text.secondary" noWrap title={item.label} sx={{ maxWidth: '70%' }}>
                {item.label}
              </Typography>
              <Typography variant="caption" fontWeight={600}>
                {item.displayValue}
              </Typography>
            </Box>
            <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
              <Box sx={{ height: '100%', width: `${widthPct}%`, bgcolor: barColor, borderRadius: 999 }} />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
