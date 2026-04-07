import type { ReactNode } from 'react';
import { Box, Paper, Typography } from '@mui/material';

export interface PlaceholderScreenScaffoldProps {
  /** Short note on what will ship here (no fake metrics). */
  roadmapNote?: string;
  /** Optional extra blocks (e.g. existing minimal UI). */
  children?: ReactNode;
}

/**
 * **Sprint 2.1 only — not a universal page layout.**
 *
 * Temporary composition scaffold for a few **top-level** placeholder routes (Review queue, Metrics, etc.).
 * It mirrors the **target block order** from Re diseño 3.3 §9.2, §9.8, §9.11 (KPI row → filter toolbar → primary
 * content) so future sprints replace pieces in place without re-architecting the shell.
 *
 * Do **not** assume every future screen uses this component: inventory detail, aisle results, and review detail
 * follow their own §9.x layouts. Page title for scaffold routes lives in `AppShell`’s topbar only.
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
