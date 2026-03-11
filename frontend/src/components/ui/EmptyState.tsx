/**
 * Empty state block: centered message in a Paper.
 * Use when a list or section has no items.
 */

import { Paper, Typography } from '@mui/material';

export interface EmptyStateProps {
  message: string;
  /** Paper padding (theme spacing units). Default 3. */
  padding?: number;
}

export default function EmptyState({ message, padding = 3 }: EmptyStateProps) {
  return (
    <Paper sx={{ p: padding, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
    </Paper>
  );
}
