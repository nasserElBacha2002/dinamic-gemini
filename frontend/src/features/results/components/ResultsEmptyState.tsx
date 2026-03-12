/**
 * Epic 3 — Empty state for the Results overview (no results at all).
 */

import { Paper, Typography } from '@mui/material';

export interface ResultsEmptyStateProps {
  message?: string;
}

export default function ResultsEmptyState({
  message = 'No results yet. Run processing on this aisle to see results.',
}: ResultsEmptyStateProps) {
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
    </Paper>
  );
}
