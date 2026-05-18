import { Box, Stack, Typography } from '@mui/material';
import type { SegmentDatum } from '../../adapters/analyticsChartDatasets';

const SEGMENT_COLORS = ['primary.main', 'warning.main', 'grey.500'] as const;

export interface SegmentBarChartProps {
  segments: readonly SegmentDatum[];
  emptyText: string;
  'data-testid'?: string;
}

export function SegmentBarChart({ segments, emptyText, 'data-testid': testId }: SegmentBarChartProps) {
  if (!segments.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box data-testid={testId}>
      <Box
        sx={{
          display: 'flex',
          height: 12,
          borderRadius: 999,
          overflow: 'hidden',
          bgcolor: 'action.hover',
          mb: 1.5,
        }}
        role="img"
        aria-label={segments.map((s) => `${s.label} ${s.pct.toFixed(1)}%`).join(', ')}
      >
        {segments.map((seg, idx) => (
          <Box
            key={seg.id}
            sx={{
              width: `${Math.max(0, seg.pct)}%`,
              bgcolor: SEGMENT_COLORS[idx % SEGMENT_COLORS.length],
              minWidth: seg.pct > 0 ? 4 : 0,
            }}
          />
        ))}
      </Box>
      <Stack spacing={0.75}>
        {segments.map((seg, idx) => (
          <Box key={seg.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                bgcolor: SEGMENT_COLORS[idx % SEGMENT_COLORS.length],
                flexShrink: 0,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {seg.label}: {seg.pct.toFixed(1)} %
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
