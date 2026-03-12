/**
 * Epic 4 — Empty / not-found state for Result Detail.
 */

import { Paper, Typography } from '@mui/material';

export interface ResultDetailEmptyStateProps {
  message?: string;
}

export default function ResultDetailEmptyState({
  message = 'Result not found or no longer available.',
}: ResultDetailEmptyStateProps) {
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
    </Paper>
  );
}
