import { Box, Typography } from '@mui/material';
import type { BarChartDatum } from '../../adapters/analyticsChartDatasets';

export interface HorizontalBarChartProps {
  data: readonly BarChartDatum[];
  emptyText: string;
  'data-testid'?: string;
  barColor?: string;
  ariaLabel?: string;
  onBarClick?: (item: BarChartDatum) => void;
}

export function HorizontalBarChart({
  data,
  emptyText,
  'data-testid': testId,
  barColor = 'primary.main',
  ariaLabel,
  onBarClick,
}: HorizontalBarChartProps) {
  if (!data.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
        {emptyText}
      </Typography>
    );
  }

  const max = Math.max(...data.map((d) => d.value), 1);
  const label = ariaLabel ?? data.map((d) => `${d.label} ${d.displayValue}`).join(', ');

  return (
    <Box
      role={onBarClick ? undefined : 'img'}
      aria-label={onBarClick ? undefined : label}
      data-testid={testId}
      sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}
    >
      {data.map((item) => {
        const widthPct = Math.max(4, (item.value / max) * 100);
        return (
          <Box
            key={item.id}
            sx={{ minWidth: 0, cursor: onBarClick ? 'pointer' : undefined }}
            data-testid={testId ? `${testId}-row-${item.id}` : undefined}
            onClick={onBarClick ? () => onBarClick(item) : undefined}
            onKeyDown={
              onBarClick
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onBarClick(item);
                    }
                  }
                : undefined
            }
            role={onBarClick ? 'button' : undefined}
            tabIndex={onBarClick ? 0 : undefined}
          >
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
