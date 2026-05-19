import { Box, Paper, Typography } from '@mui/material';

export interface CompactKpiItem {
  id: string;
  label: string;
  value: string;
}

export interface AnalyticsCompactKpiGridProps {
  items: readonly CompactKpiItem[];
  'data-testid'?: string;
}

export function AnalyticsCompactKpiGrid({ items, 'data-testid': testId }: AnalyticsCompactKpiGridProps) {
  if (!items.length) return null;

  return (
    <Box
      data-testid={testId}
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: `repeat(${Math.min(items.length, 4)}, minmax(0, 1fr))` },
        gap: 1.5,
      }}
    >
      {items.map((item) => (
        <Paper
          key={item.id}
          variant="outlined"
          data-testid={testId ? `${testId}-${item.id}` : undefined}
          sx={{ p: 1.5, minWidth: 0 }}
        >
          <Typography variant="caption" color="text.secondary" display="block" noWrap title={item.label}>
            {item.label}
          </Typography>
          <Typography variant="h6" fontWeight={700} sx={{ mt: 0.25 }}>
            {item.value}
          </Typography>
        </Paper>
      ))}
    </Box>
  );
}
