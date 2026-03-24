import type { ReactNode } from 'react';
import { Box, Paper, Typography } from '@mui/material';

export interface PlaceholderScreenScaffoldProps {
  /** Short note on what will ship here (no fake metrics). */
  roadmapNote?: string;
  /** Optional extra blocks (e.g. existing minimal UI). */
  children?: ReactNode;
}

/**
 * Structural placeholder for Dashboard, Review queue, Metrics, etc.
 * Mirrors target composition from Re diseño 3.3 §9.2, §9.8, §9.11: KPI strip → filters → main block — without fabricated data.
 * Page title lives in the app topbar (AppShell); this block is layout-only below it.
 */
export default function PlaceholderScreenScaffold({ roadmapNote, children }: PlaceholderScreenScaffoldProps) {
  return (
    <>
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', md: 'repeat(4, 1fr)' },
          mb: 2,
        }}
      >
        {[0, 1, 2, 3].map((i) => (
          <Paper
            key={i}
            variant="outlined"
            sx={{
              p: 2,
              minHeight: 88,
              bgcolor: 'background.paper',
              borderStyle: 'dashed',
            }}
          >
            <Typography variant="caption" color="text.secondary">
              KPI
            </Typography>
            <Typography variant="body2" color="text.disabled" sx={{ mt: 0.5 }}>
              —
            </Typography>
          </Paper>
        ))}
      </Box>
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          mb: 2,
          borderStyle: 'dashed',
          bgcolor: 'grey.50',
        }}
      >
        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
          Filters / search (toolbar)
        </Typography>
        <Typography variant="body2" color="text.disabled">
          Reserved for FilterToolbar — Sprint 2.3+.
        </Typography>
      </Paper>
      <Paper variant="outlined" sx={{ p: 3, minHeight: 200, borderStyle: 'dashed' }}>
        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
          Primary content
        </Typography>
        {roadmapNote ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {roadmapNote}
          </Typography>
        ) : null}
        {children}
      </Paper>
    </>
  );
}
