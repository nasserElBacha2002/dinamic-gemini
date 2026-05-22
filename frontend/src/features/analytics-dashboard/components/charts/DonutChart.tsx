import { Box, Stack, Typography } from '@mui/material';

export interface DonutSegment {
  id: string;
  label: string;
  value: number;
  displayValue: string;
}

const SEGMENT_COLORS = ['#1976d2', '#ed6c02', '#0288d1', '#9e9e9e', '#2e7d32'] as const;

export interface DonutChartProps {
  segments: readonly DonutSegment[];
  emptyText: string;
  size?: number;
  'data-testid'?: string;
}

function buildConicGradient(segments: readonly DonutSegment[]): string {
  const total = segments.reduce((sum, seg) => sum + Math.max(0, seg.value), 0);
  if (total <= 0) return 'transparent';
  let cursor = 0;
  const stops: string[] = [];
  segments.forEach((seg, index) => {
    const pct = (Math.max(0, seg.value) / total) * 100;
    if (pct <= 0) return;
    const color = SEGMENT_COLORS[index % SEGMENT_COLORS.length];
    const start = cursor;
    const end = cursor + pct;
    stops.push(`${color} ${start}% ${end}%`);
    cursor = end;
  });
  return `conic-gradient(${stops.join(', ')})`;
}

export function DonutChart({ segments, emptyText, size = 112, 'data-testid': testId }: DonutChartProps) {
  const total = segments.reduce((sum, seg) => sum + Math.max(0, seg.value), 0);

  if (!segments.length || total <= 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
        {emptyText}
      </Typography>
    );
  }

  const ariaLabel = segments.map((s) => `${s.label} ${s.displayValue}`).join(', ');
  const gradient = buildConicGradient(segments);

  return (
    <Box
      data-testid={testId}
      sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}
    >
      <Box
        role="img"
        aria-label={ariaLabel}
        sx={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: gradient,
          position: 'relative',
          flexShrink: 0,
          '&::after': {
            content: '""',
            position: 'absolute',
            inset: '22%',
            borderRadius: '50%',
            bgcolor: 'background.paper',
          },
        }}
      />
      <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1 }}>
        {segments.map((seg, index) => (
          <Box key={seg.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                bgcolor: SEGMENT_COLORS[index % SEGMENT_COLORS.length],
                flexShrink: 0,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {seg.label}: {seg.displayValue}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
