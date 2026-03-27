import { Box, Typography } from '@mui/material';
import type { AnalyticsTrendPoint } from '../types';

export interface TrendBarsProps {
  title: string;
  subtitle?: string;
  /** Uses `reviewed_results` as bar height (normalized). */
  points: AnalyticsTrendPoint[];
  emptyMessage?: string;
}

export default function TrendBars({ title, subtitle, points, emptyMessage }: TrendBarsProps) {
  const max = Math.max(1, ...points.map((p) => p.reviewed_results));

  if (!points.length) {
    return (
      <Box sx={{ py: 2 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {subtitle}
          </Typography>
        ) : null}
        <Typography variant="body2" color="text.secondary">
          {emptyMessage ?? 'No trend data for this range. Trends require date_from and date_to on the backend.'}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {title}
      </Typography>
      {subtitle ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
          {subtitle}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.5, minHeight: 120, px: 0.5 }}>
        {points.map((p) => {
          const hPct = (p.reviewed_results / max) * 100;
          return (
            <Box
              key={p.period}
              sx={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                minWidth: 0,
              }}
              title={`${p.period}: ${p.reviewed_results}`}
            >
              <Box
                sx={{
                  width: '100%',
                  maxWidth: 28,
                  height: `${Math.max(8, hPct)}%`,
                  minHeight: 4,
                  bgcolor: 'primary.main',
                  borderRadius: 0.5,
                  opacity: 0.85,
                }}
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontSize: '0.65rem', mt: 0.5, transform: 'rotate(-45deg)', transformOrigin: 'top center' }}
                noWrap
              >
                {p.period.slice(5)}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
